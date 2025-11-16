from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fakeredis.aioredis import FakeRedis

from co_sim.core import redis as redis_helpers
from co_sim.schemas.session import SessionRead
from co_sim.services import session_cache


def _session_read(*, workspace_id: UUID, status: str) -> SessionRead:
    now = datetime.now(timezone.utc)
    return SessionRead(
        id=uuid4(),
        workspace_id=workspace_id,
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


@pytest.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


@pytest.mark.asyncio
async def test_upsert_and_get_session():
    workspace = uuid4()
    session_read = _session_read(workspace_id=workspace, status="running")

    await session_cache.upsert_session(session_read, emit_event=False)
    cached = await session_cache.get_session(session_read.id)

    assert cached is not None
    assert cached.id == session_read.id
    assert cached.workspace_id == workspace


@pytest.mark.asyncio
async def test_list_sessions_filters():
    workspace_a = uuid4()
    workspace_b = uuid4()
    session_a = _session_read(workspace_id=workspace_a, status="running")
    session_b = _session_read(workspace_id=workspace_b, status="paused")

    await session_cache.upsert_sessions([session_a, session_b], emit_event=False)

    all_sessions = await session_cache.list_sessions()
    assert all_sessions is not None
    ids = {s.id for s in all_sessions}
    assert session_a.id in ids and session_b.id in ids

    workspace_filtered = await session_cache.list_sessions(workspace_id=workspace_a)
    assert workspace_filtered is not None
    assert len(workspace_filtered) == 1 and workspace_filtered[0].id == session_a.id

    status_filtered = await session_cache.list_sessions(status="paused")
    assert status_filtered is not None
    assert len(status_filtered) == 1 and status_filtered[0].id == session_b.id


@pytest.mark.asyncio
async def test_list_sessions_returns_none_when_missing_payload():
    workspace = uuid4()
    session_read = _session_read(workspace_id=workspace, status="running")
    await session_cache.upsert_session(session_read, emit_event=False)

    redis = await redis_helpers.get_redis()
    await redis.delete(f"sessions:data:{session_read.id}")

    cached = await session_cache.list_sessions()
    assert cached is None
