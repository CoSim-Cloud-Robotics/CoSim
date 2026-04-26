"""Tests for the shared sim-control service.

Collaborators jointly drive a workspace's simulation by applying commands
(start/stop/reset/seed/update_params) against a shared state document. The
service stores the document in Redis with a monotonic ``version`` counter so
that frontend Yjs clients (and headless agents) can converge on the same
ground truth. Each applied command is published to a Redis channel and
appended to a bounded history list.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from co_sim.core import redis as redis_helpers


@pytest_asyncio.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


# ---------------------------------------------------------------------------
# initial state / get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_state_creates_default_when_missing():
    from co_sim.services.sim_control import get_state

    state = await get_state(workspace_id="ws-1")
    assert state.workspace_id == "ws-1"
    assert state.status == "idle"
    assert state.version == 0
    assert state.seed is None
    assert state.params == {}


@pytest.mark.asyncio
async def test_initialize_state_overrides_defaults():
    from co_sim.services.sim_control import initialize_state, get_state

    await initialize_state(
        workspace_id="ws-1",
        engine="pybullet",
        seed=42,
        params={"max_steps": 1000},
    )
    state = await get_state(workspace_id="ws-1")
    assert state.engine == "pybullet"
    assert state.seed == 42
    assert state.params == {"max_steps": 1000}
    assert state.version == 1


# ---------------------------------------------------------------------------
# apply_command — start/stop/reset/seed/update_params
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_start_transitions_to_running():
    from co_sim.services.sim_control import apply_command, get_state

    result = await apply_command(workspace_id="ws-1", command="start", actor="ada")
    assert result.status == "running"
    assert result.version == 1
    assert result.last_actor == "ada"

    state = await get_state(workspace_id="ws-1")
    assert state.status == "running"
    assert state.version == 1


@pytest.mark.asyncio
async def test_apply_stop_after_start():
    from co_sim.services.sim_control import apply_command

    await apply_command(workspace_id="ws-1", command="start", actor="ada")
    stopped = await apply_command(workspace_id="ws-1", command="stop", actor="bob")
    assert stopped.status == "stopped"
    assert stopped.version == 2
    assert stopped.last_actor == "bob"


@pytest.mark.asyncio
async def test_apply_reset_clears_runtime_metrics():
    from co_sim.services.sim_control import apply_command

    await apply_command(workspace_id="ws-1", command="start", actor="ada")
    await apply_command(
        workspace_id="ws-1",
        command="update_params",
        actor="ada",
        params={"frame": 250, "max_steps": 500},
    )
    reset = await apply_command(workspace_id="ws-1", command="reset", actor="ada")
    assert reset.status == "idle"
    # Reset preserves user-provided params (max_steps) but clears runtime fields.
    assert reset.params.get("max_steps") == 500
    assert "frame" not in reset.params


@pytest.mark.asyncio
async def test_apply_seed_records_seed():
    from co_sim.services.sim_control import apply_command

    seeded = await apply_command(
        workspace_id="ws-1", command="seed", actor="ada", seed=1234
    )
    assert seeded.seed == 1234


@pytest.mark.asyncio
async def test_apply_update_params_merges():
    from co_sim.services.sim_control import apply_command

    await apply_command(
        workspace_id="ws-1",
        command="update_params",
        actor="ada",
        params={"alpha": 1, "beta": 2},
    )
    merged = await apply_command(
        workspace_id="ws-1",
        command="update_params",
        actor="bob",
        params={"beta": 9, "gamma": 3},
    )
    assert merged.params == {"alpha": 1, "beta": 9, "gamma": 3}
    assert merged.version == 2


@pytest.mark.asyncio
async def test_unknown_command_raises():
    from co_sim.services.sim_control import apply_command

    with pytest.raises(ValueError):
        await apply_command(workspace_id="ws-1", command="explode", actor="ada")


@pytest.mark.asyncio
async def test_seed_command_requires_seed():
    from co_sim.services.sim_control import apply_command

    with pytest.raises(ValueError):
        await apply_command(workspace_id="ws-1", command="seed", actor="ada")


# ---------------------------------------------------------------------------
# CRDT-style version monotonicity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_version_is_monotonic_under_concurrent_commands():
    import asyncio

    from co_sim.services.sim_control import apply_command, get_state

    # Apply several commands concurrently — all updates must produce
    # monotonically increasing versions.
    await asyncio.gather(
        apply_command(workspace_id="ws-1", command="start", actor="ada"),
        apply_command(workspace_id="ws-1", command="stop", actor="bob"),
        apply_command(workspace_id="ws-1", command="reset", actor="cleo"),
        apply_command(workspace_id="ws-1", command="seed", actor="dave", seed=7),
    )
    state = await get_state(workspace_id="ws-1")
    assert state.version == 4


# ---------------------------------------------------------------------------
# history + pub/sub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_records_commands_in_order():
    from co_sim.services.sim_control import apply_command, list_history

    await apply_command(workspace_id="ws-1", command="start", actor="ada")
    await apply_command(workspace_id="ws-1", command="stop", actor="bob")
    history = await list_history(workspace_id="ws-1")
    assert [entry.command for entry in history] == ["start", "stop"]
    assert [entry.actor for entry in history] == ["ada", "bob"]


@pytest.mark.asyncio
async def test_apply_publishes_event():
    from co_sim.services import sim_control

    pubsub = await redis_helpers.subscribe(sim_control.sim_control_channel("ws-1"))
    try:
        await pubsub.get_message(timeout=0.1)

        await sim_control.apply_command(
            workspace_id="ws-1", command="start", actor="ada"
        )

        for _ in range(20):
            msg = await pubsub.get_message(timeout=0.1)
            if msg and msg.get("type") == "message":
                break
        else:  # pragma: no cover - timing safeguard
            pytest.fail("no sim-control event received")

        payload = json.loads(msg["data"])
        assert payload["command"] == "start"
        assert payload["actor"] == "ada"
        assert payload["version"] == 1
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()
