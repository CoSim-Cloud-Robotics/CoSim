from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fakeredis.aioredis import FakeRedis

os.environ.setdefault("COSIM_JWT_SECRET_KEY", "x" * 32)

from co_sim.core import redis as redis_helpers
from co_sim.services import session_events
from co_sim.services import session_cache
from co_sim.agents.simulation import session_tracker
from co_sim.schemas.session import SessionRead


@pytest.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await session_events.stop_listener()
    await redis_helpers.reset_redis_state()


def _session_read(status: str) -> SessionRead:
    now = datetime.now(timezone.utc)
    return SessionRead(
        id=uuid4(),
        workspace_id=uuid4(),
        session_type="ide",
        status=status,
        requested_gpu=None,
        details={},
        started_at=None,
        ended_at=None,
        participants=[],
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_emit_event_notifies_handlers_and_records_history():
    events_handled = []

    def handler(event: dict) -> None:
        events_handled.append(event)

    session_events.register_handler("unit", handler)

    payload = {"type": "session.created", "session": {"id": "abc", "status": "running"}}
    await session_events.emit_event(payload)

    assert events_handled and events_handled[0]["session"]["id"] == "abc"
    assert session_events.get_recent_events(limit=1)[0]["session"]["status"] == "running"

    session_events.unregister_handler("unit")


@pytest.mark.asyncio
async def test_session_transition_updates_simulation_tracker(monkeypatch):
    async def fake_publish(channel, message):
        await session_events.emit_event(json.loads(message))
        return 1

    monkeypatch.setattr(session_cache, "publish", fake_publish)
    session_events.register_handler("sim-test", session_tracker.handle_session_event)

    session_obj = _session_read(status="running")
    await session_cache.upsert_session(session_obj, event_type="session.created")

    active = session_tracker.get_active_sessions()
    assert active and active[0]["id"] == str(session_obj.id)

    updated = session_obj.model_copy(update={"status": "terminated"})
    await session_cache.upsert_session(updated, event_type="session.terminated")

    assert session_tracker.get_active_sessions() == []

    session_events.unregister_handler("sim-test")
