from __future__ import annotations

import json
from typing import Iterable
from uuid import UUID

from co_sim.core.redis import get_redis, publish
from co_sim.models.session import SessionStatus
from co_sim.schemas.session import SessionRead

_DATA_KEY = "sessions:data"
_ALL_KEY = "sessions:all"
_WORKSPACE_KEY = "sessions:workspace"
_STATUS_KEY = "sessions:status"
SESSION_EVENTS_CHANNEL = "sessions:events"


def _session_data_key(session_id: str | UUID) -> str:
    return f"{_DATA_KEY}:{session_id}"


def _all_sessions_key() -> str:
    return _ALL_KEY


def _workspace_key(workspace_id: UUID) -> str:
    return f"{_WORKSPACE_KEY}:{workspace_id}"


def _status_key(status: SessionStatus | str) -> str:
    value = status.value if isinstance(status, SessionStatus) else str(status)
    return f"{_STATUS_KEY}:{value}"


async def upsert_session(session_read: SessionRead, *, event_type: str = "session.updated", emit_event: bool = True) -> None:
    redis = await get_redis()
    session_id = str(session_read.id)
    key = _session_data_key(session_id)
    payload = session_read.model_dump_json()
    previous = await redis.get(key)

    pipe = redis.pipeline()
    pipe.set(key, payload)
    pipe.sadd(_all_sessions_key(), session_id)
    pipe.sadd(_workspace_key(session_read.workspace_id), session_id)
    pipe.sadd(_status_key(session_read.status), session_id)

    if previous:
        previous_model = SessionRead.model_validate_json(previous)
        if previous_model.workspace_id != session_read.workspace_id:
            pipe.srem(_workspace_key(previous_model.workspace_id), session_id)
        if previous_model.status != session_read.status:
            pipe.srem(_status_key(previous_model.status), session_id)

    await pipe.execute()

    if emit_event:
        await publish(
            SESSION_EVENTS_CHANNEL,
            json.dumps({"type": event_type, "session": json.loads(payload)}),
        )


async def upsert_sessions(sessions: Iterable[SessionRead], *, emit_event: bool = False) -> None:
    for session in sessions:
        await upsert_session(session, emit_event=emit_event, event_type="session.synced")


async def get_session(session_id: UUID) -> SessionRead | None:
    redis = await get_redis()
    payload = await redis.get(_session_data_key(session_id))
    if not payload:
        return None
    return SessionRead.model_validate_json(payload)


async def list_sessions(
    workspace_id: UUID | None = None,
    status: SessionStatus | None = None,
) -> list[SessionRead] | None:
    redis = await get_redis()
    if not await redis.exists(_all_sessions_key()):
        return None

    candidate_ids: set[str] | None = None

    if workspace_id:
        workspace_key = _workspace_key(workspace_id)
        if not await redis.exists(workspace_key):
            return None
        workspace_members = await redis.smembers(workspace_key)
        candidate_ids = set(workspace_members)
    else:
        all_members = await redis.smembers(_all_sessions_key())
        candidate_ids = set(all_members)

    if status:
        status_key = _status_key(status)
        if not await redis.exists(status_key):
            return None
        status_members = await redis.smembers(status_key)
        candidate_ids = {sid for sid in candidate_ids if sid in status_members}

    if not candidate_ids:
        return []

    pipe = redis.pipeline()
    ordered_ids = sorted(candidate_ids)
    for session_id in ordered_ids:
        pipe.get(_session_data_key(session_id))
    payloads = await pipe.execute()

    entries: list[SessionRead] = []
    for payload in payloads:
        if not payload:
            return None
        entries.append(SessionRead.model_validate_json(payload))

    entries.sort(key=lambda s: s.created_at)
    return entries
