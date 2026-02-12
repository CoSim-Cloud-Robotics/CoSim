from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.api.dependencies import get_current_user
from co_sim.db.session import get_db
from co_sim.models.session import SessionStatus
from co_sim.models.user import User
from co_sim.schemas.session import (
    SessionCreate,
    SessionParticipantCreate,
    SessionParticipantRead,
    SessionRead,
    SessionUpdate,
)
from co_sim.services import sessions as session_service
from co_sim.typing import Annotated

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SessionRead:
    return await session_service.create_session(session, payload)


@router.get("", response_model=List[SessionRead])
async def list_sessions(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    workspace_id: UUID | None = Query(default=None),
    status_filter: SessionStatus | None = Query(default=None, alias="status"),
) -> list[SessionRead]:
    return await session_service.list_sessions(session, workspace_id=workspace_id, status=status_filter)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SessionRead:
    session_read = await session_service.get_session_cached(session, session_id)
    if not session_read:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session_read


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(
    session_id: UUID,
    payload: SessionUpdate,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SessionRead:
    db_session = await session_service.get_session(session, session_id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return await session_service.update_session(session, db_session, payload)


@router.post("/{session_id}/pause", response_model=SessionRead)
async def pause_session(
    session_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SessionRead:
    db_session = await session_service.get_session(session, session_id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return await session_service.transition_status(session, db_session, SessionStatus.PAUSED)


@router.post("/{session_id}/resume", response_model=SessionRead)
async def resume_session(
    session_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SessionRead:
    db_session = await session_service.get_session(session, session_id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return await session_service.transition_status(session, db_session, SessionStatus.RUNNING)


@router.post("/{session_id}/terminate", response_model=SessionRead)
async def terminate_session(
    session_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SessionRead:
    db_session = await session_service.get_session(session, session_id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return await session_service.transition_status(session, db_session, SessionStatus.TERMINATED)


@router.post("/{session_id}/participants", response_model=SessionParticipantRead, status_code=status.HTTP_201_CREATED)
async def add_session_participant(
    session_id: UUID,
    payload: SessionParticipantCreate,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SessionParticipantRead:
    db_session = await session_service.get_session(session, session_id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return await session_service.add_participant(session, db_session, payload)
