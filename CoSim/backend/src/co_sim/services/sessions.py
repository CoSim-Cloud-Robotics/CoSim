from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.models.session import Session, SessionParticipant, SessionStatus
from co_sim.schemas.session import (
    SessionCreate,
    SessionParticipantCreate,
    SessionParticipantRead,
    SessionRead,
    SessionUpdate,
)
from co_sim.services import session_cache


async def create_session(session: AsyncSession, payload: SessionCreate) -> SessionRead:
    db_session = Session(
        workspace_id=payload.workspace_id,
        session_type=payload.session_type,
        requested_gpu=payload.requested_gpu,
        details=payload.details,
    )
    session.add(db_session)
    await session.commit()
    await session.refresh(db_session)
    session_read = await serialize_session(session, db_session)
    await session_cache.upsert_session(session_read, event_type="session.created")
    return session_read


async def list_sessions(
    session: AsyncSession,
    workspace_id: UUID | None = None,
    status: SessionStatus | None = None,
) -> list[SessionRead]:
    cached = await session_cache.list_sessions(workspace_id=workspace_id, status=status)
    if cached is not None:
        return cached

    query = select(Session)
    if workspace_id:
        query = query.where(Session.workspace_id == workspace_id)
    if status:
        query = query.where(Session.status == status)
    result = await session.execute(query)
    sessions = result.scalars().all()
    serialized = [await serialize_session(session, s) for s in sessions]
    await session_cache.upsert_sessions(serialized, emit_event=False)
    return serialized


async def get_session(session: AsyncSession, session_id: UUID) -> Session | None:
    result = await session.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def update_session(
    session: AsyncSession,
    db_session: Session,
    payload: SessionUpdate,
) -> SessionRead:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(db_session, field, value)
    if "status" in data and data["status"] in {SessionStatus.RUNNING, SessionStatus.STARTING}:
        db_session.started_at = datetime.now(timezone.utc)
    if "status" in data and data["status"] in {SessionStatus.TERMINATED}:
        db_session.ended_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(db_session)
    session_read = await serialize_session(session, db_session)
    await session_cache.upsert_session(session_read, event_type="session.updated")
    return session_read


async def transition_status(
    session: AsyncSession,
    db_session: Session,
    status: SessionStatus,
) -> SessionRead:
    return await update_session(session, db_session, SessionUpdate(status=status))


async def add_participant(
    session: AsyncSession,
    db_session: Session,
    payload: SessionParticipantCreate,
) -> SessionParticipantRead:
    participant = SessionParticipant(session_id=db_session.id, user_id=payload.user_id, role=payload.role)
    session.add(participant)
    await session.commit()
    await session.refresh(participant)
    participant_read = SessionParticipantRead.model_validate(participant)
    serialized = await serialize_session(session, db_session)
    await session_cache.upsert_session(serialized, event_type="session.participant")
    return participant_read


async def serialize_session(session: AsyncSession, db_session: Session) -> SessionRead:
    await session.refresh(db_session, attribute_names=["participants"])
    participants = [SessionParticipantRead.model_validate(p) for p in db_session.participants]
    base = SessionRead.model_validate(db_session)
    return base.model_copy(update={"participants": participants})


async def get_session_cached(session: AsyncSession, session_id: UUID) -> SessionRead | None:
    cached = await session_cache.get_session(session_id)
    if cached:
        return cached
    db_session = await get_session(session, session_id)
    if not db_session:
        return None
    serialized = await serialize_session(session, db_session)
    await session_cache.upsert_session(serialized, emit_event=False)
    return serialized
