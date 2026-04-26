"""Tests for the TensorBoard streaming service.

The service does three things:

1. ``write_metrics`` appends scalar metrics to a per-run JSONL file inside a
   workspace logdir (a TensorBoardX/SummaryWriter compatible event file is
   also written when ``tensorboardX`` is importable; we don't require it for
   tests).
2. ``start_stream`` launches a ``tensorboard`` subprocess and stores its
   coordinates (port, pid, logdir) in Redis. Tests inject a fake spawner.
3. ``drain_training_history`` re-hydrates a logdir from the existing
   RL training metrics history persisted in Redis.
"""
from __future__ import annotations

import json
from pathlib import Path

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
# Logdir + metric writing
# ---------------------------------------------------------------------------


def test_resolve_logdir_under_workspace(tmp_path):
    from co_sim.services.tensorboard_stream import resolve_logdir

    logdir = resolve_logdir(workspace_id="ws-1", run_id="run-1", root=tmp_path)
    assert logdir.is_relative_to(tmp_path)
    assert "ws-1" in str(logdir)
    assert "run-1" in str(logdir)


@pytest.mark.asyncio
async def test_write_metrics_appends_to_jsonl(tmp_path):
    from co_sim.services.tensorboard_stream import write_metrics, resolve_logdir

    await write_metrics(
        workspace_id="ws-1",
        run_id="run-1",
        timestep=10,
        scalars={"reward": 1.5, "loss": 0.2},
        root=tmp_path,
    )
    await write_metrics(
        workspace_id="ws-1",
        run_id="run-1",
        timestep=20,
        scalars={"reward": 2.0},
        root=tmp_path,
    )

    logdir = resolve_logdir(workspace_id="ws-1", run_id="run-1", root=tmp_path)
    jsonl = logdir / "metrics.jsonl"
    assert jsonl.exists()
    lines = jsonl.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["timestep"] == 10
    assert first["scalars"]["reward"] == 1.5


@pytest.mark.asyncio
async def test_write_metrics_rejects_path_traversal(tmp_path):
    from co_sim.services.tensorboard_stream import write_metrics

    with pytest.raises(ValueError):
        await write_metrics(
            workspace_id="../escape",
            run_id="run-1",
            timestep=1,
            scalars={"reward": 1.0},
            root=tmp_path,
        )


# ---------------------------------------------------------------------------
# start_stream / stop_stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_stream_records_metadata(tmp_path):
    from co_sim.services import tensorboard_stream as tb

    spawned: dict = {}

    class _FakeProcess:
        def __init__(self, pid: int):
            self.pid = pid
            self.returncode = None

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    async def fake_spawner(*, logdir: Path, port: int):
        spawned["logdir"] = logdir
        spawned["port"] = port
        return _FakeProcess(pid=4242)

    info = await tb.start_stream(
        workspace_id="ws-1",
        run_id="run-1",
        port=6006,
        root=tmp_path,
        spawner=fake_spawner,
    )
    assert info.port == 6006
    assert info.pid == 4242
    assert spawned["port"] == 6006
    assert "ws-1" in str(spawned["logdir"])

    state = await tb.get_stream_state(workspace_id="ws-1", run_id="run-1")
    assert state is not None
    assert state["port"] == "6006"
    assert state["pid"] == "4242"
    assert state["status"] == "running"


@pytest.mark.asyncio
async def test_stop_stream_terminates_and_clears_state(tmp_path):
    from co_sim.services import tensorboard_stream as tb

    terminated = {"called": 0}

    class _FakeProcess:
        def __init__(self):
            self.pid = 7777
            self.returncode = None

        def terminate(self) -> None:
            terminated["called"] += 1
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    async def fake_spawner(*, logdir: Path, port: int):
        return _FakeProcess()

    await tb.start_stream(
        workspace_id="ws-1",
        run_id="run-1",
        port=6006,
        root=tmp_path,
        spawner=fake_spawner,
    )
    stopped = await tb.stop_stream(workspace_id="ws-1", run_id="run-1")
    assert stopped is True
    assert terminated["called"] == 1
    assert await tb.get_stream_state(workspace_id="ws-1", run_id="run-1") is None


@pytest.mark.asyncio
async def test_stop_stream_unknown_returns_false(tmp_path):
    from co_sim.services import tensorboard_stream as tb

    assert await tb.stop_stream(workspace_id="nope", run_id="nope") is False


@pytest.mark.asyncio
async def test_list_active_streams(tmp_path):
    from co_sim.services import tensorboard_stream as tb

    class _FakeProcess:
        def __init__(self, pid):
            self.pid = pid
            self.returncode = None

        def terminate(self):
            self.returncode = 0

        def kill(self):
            self.returncode = -9

        async def wait(self):
            return self.returncode or 0

    async def fake_spawner(*, logdir: Path, port: int):
        return _FakeProcess(pid=port)

    await tb.start_stream(
        workspace_id="ws-1", run_id="run-a", port=6006, root=tmp_path, spawner=fake_spawner
    )
    await tb.start_stream(
        workspace_id="ws-1", run_id="run-b", port=6007, root=tmp_path, spawner=fake_spawner
    )
    await tb.start_stream(
        workspace_id="ws-2", run_id="run-c", port=6008, root=tmp_path, spawner=fake_spawner
    )
    streams = await tb.list_active_streams(workspace_id="ws-1")
    assert {entry["run_id"] for entry in streams} == {"run-a", "run-b"}


# ---------------------------------------------------------------------------
# drain_training_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drain_training_history_writes_jsonl(tmp_path):
    """Existing RL training metrics in Redis are mirrored into the logdir."""
    from co_sim.services import tensorboard_stream as tb
    from co_sim.services import rl_training_agent as rl

    await rl.persist_training_metrics(
        run_id="run-1", timestep=10, episode=1, mean_reward=0.5
    )
    await rl.persist_training_metrics(
        run_id="run-1", timestep=20, episode=2, mean_reward=1.0
    )

    count = await tb.drain_training_history(
        workspace_id="ws-1", run_id="run-1", root=tmp_path
    )
    assert count == 2

    jsonl = tb.resolve_logdir(workspace_id="ws-1", run_id="run-1", root=tmp_path) / "metrics.jsonl"
    assert jsonl.exists()
    lines = jsonl.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["timestep"] == 10
    assert first["scalars"]["mean_reward"] == 0.5
    assert first["scalars"]["episode"] == 1
