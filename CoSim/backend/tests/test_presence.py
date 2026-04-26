"""Tests for workspace presence service.

The presence service tracks who is currently active in a workspace so the
frontend can render collaborator avatars and resolve user metadata that goes
beyond the per-document Yjs awareness already used inside the Monaco editor.

Behaviours covered:
- register/heartbeat updates a presence record (with TTL refresh)
- list_presence returns active records with filtering by TTL
- remove_presence removes a single user; remove_workspace clears all
- pub/sub channel emits presence change events
"""
from __future__ import annotations

import asyncio
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
# register / heartbeat / list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_presence_creates_record():
    from co_sim.services.presence import register_presence, list_presence

    record = await register_presence(
        workspace_id="ws-1",
        user_id="u-1",
        name="Ada",
        color="#ff00aa",
        avatar_url="https://example.com/ada.png",
        active_file="src/main.py",
    )

    assert record.user_id == "u-1"
    assert record.name == "Ada"
    assert record.color == "#ff00aa"
    assert record.avatar_url == "https://example.com/ada.png"
    assert record.active_file == "src/main.py"
    assert record.last_seen > 0

    listing = await list_presence("ws-1")
    assert len(listing) == 1
    assert listing[0].user_id == "u-1"


@pytest.mark.asyncio
async def test_heartbeat_refreshes_last_seen():
    from co_sim.services.presence import register_presence, heartbeat_presence

    first = await register_presence(workspace_id="ws-1", user_id="u-1", name="Ada", color="#fff")
    await asyncio.sleep(0.02)
    refreshed = await heartbeat_presence(workspace_id="ws-1", user_id="u-1")
    assert refreshed is not None
    assert refreshed.last_seen >= first.last_seen


@pytest.mark.asyncio
async def test_heartbeat_unknown_returns_none():
    from co_sim.services.presence import heartbeat_presence

    assert await heartbeat_presence(workspace_id="ws-x", user_id="ghost") is None


@pytest.mark.asyncio
async def test_list_presence_isolates_workspaces():
    from co_sim.services.presence import register_presence, list_presence

    await register_presence(workspace_id="ws-1", user_id="u-1", name="A", color="#1")
    await register_presence(workspace_id="ws-2", user_id="u-2", name="B", color="#2")

    ws1 = await list_presence("ws-1")
    ws2 = await list_presence("ws-2")
    assert {p.user_id for p in ws1} == {"u-1"}
    assert {p.user_id for p in ws2} == {"u-2"}


@pytest.mark.asyncio
async def test_list_presence_drops_stale_entries():
    from co_sim.services import presence

    await presence.register_presence(workspace_id="ws-1", user_id="u-1", name="A", color="#1")
    # Manually rewrite the record with an old last_seen.
    redis = await redis_helpers.get_redis()
    raw = await redis.hget("cosim:presence:ws-1", "u-1")
    payload = json.loads(raw)
    payload["last_seen"] = 0  # 1970
    await redis.hset("cosim:presence:ws-1", "u-1", json.dumps(payload))

    active = await presence.list_presence("ws-1", active_within_seconds=30)
    assert active == []


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_presence_drops_user():
    from co_sim.services.presence import register_presence, list_presence, remove_presence

    await register_presence(workspace_id="ws-1", user_id="u-1", name="A", color="#1")
    await register_presence(workspace_id="ws-1", user_id="u-2", name="B", color="#2")
    removed = await remove_presence(workspace_id="ws-1", user_id="u-1")
    assert removed is True

    remaining = await list_presence("ws-1")
    assert {p.user_id for p in remaining} == {"u-2"}


@pytest.mark.asyncio
async def test_remove_workspace_clears_all():
    from co_sim.services.presence import register_presence, list_presence, remove_workspace

    await register_presence(workspace_id="ws-1", user_id="u-1", name="A", color="#1")
    await register_presence(workspace_id="ws-1", user_id="u-2", name="B", color="#2")

    cleared = await remove_workspace("ws-1")
    assert cleared >= 2
    assert await list_presence("ws-1") == []


# ---------------------------------------------------------------------------
# pub/sub events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_publishes_event():
    from co_sim.services import presence

    pubsub = await redis_helpers.subscribe(presence.presence_channel("ws-1"))
    try:
        # Drain the initial subscription confirmation message.
        await pubsub.get_message(timeout=0.1)

        await presence.register_presence(
            workspace_id="ws-1", user_id="u-1", name="A", color="#fff"
        )

        for _ in range(20):
            msg = await pubsub.get_message(timeout=0.1)
            if msg and msg.get("type") == "message":
                break
        else:  # pragma: no cover - timing safeguard
            pytest.fail("no presence event received")

        payload = json.loads(msg["data"])
        assert payload["action"] == "register"
        assert payload["user_id"] == "u-1"
        assert payload["workspace_id"] == "ws-1"
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()


@pytest.mark.asyncio
async def test_remove_publishes_event():
    from co_sim.services import presence

    await presence.register_presence(workspace_id="ws-1", user_id="u-1", name="A", color="#1")

    pubsub = await redis_helpers.subscribe(presence.presence_channel("ws-1"))
    try:
        await pubsub.get_message(timeout=0.1)
        await presence.remove_presence(workspace_id="ws-1", user_id="u-1")

        for _ in range(20):
            msg = await pubsub.get_message(timeout=0.1)
            if msg and msg.get("type") == "message":
                break
        else:  # pragma: no cover - timing safeguard
            pytest.fail("no remove event received")

        payload = json.loads(msg["data"])
        assert payload["action"] == "remove"
        assert payload["user_id"] == "u-1"
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()
