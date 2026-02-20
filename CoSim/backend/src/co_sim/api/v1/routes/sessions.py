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
from co_sim.schemas.debug import DebugSessionInfo, DebugStartRequest, DebugStopResponse
from co_sim.services import sessions as session_service
from co_sim.services import debug_sessions as debug_service
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


@router.post("/{session_id}/debug/start", response_model=DebugSessionInfo, status_code=status.HTTP_201_CREATED)
async def start_debug_session(
    session_id: UUID,
    payload: DebugStartRequest,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DebugSessionInfo:
    db_session = await session_service.get_session(session, session_id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    try:
        debug_session = await debug_service.start_debug_session(
            session,
            session_id=str(session_id),
            workspace_id=db_session.workspace_id,
            language=payload.language,
            file_path=payload.file_path,
            binary_path=payload.binary_path,
            args=payload.args,
            adapter=payload.adapter,
            port=payload.port,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return DebugSessionInfo(
        debug_id=debug_session.debug_id,
        language=debug_session.language,
        adapter=debug_session.adapter,
        port=debug_session.port,
        command=debug_session.command,
        working_dir=debug_session.working_dir,
    )


@router.post("/{session_id}/debug/{debug_id}/stop", response_model=DebugStopResponse)
async def stop_debug_session(
    session_id: UUID,
    debug_id: str,
    _: Annotated[User, Depends(get_current_user)],
) -> DebugStopResponse:
    _ = session_id
    stopped = await debug_service.stop_debug_session(debug_id)
    if not stopped:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debug session not found")
    return DebugStopResponse(status="stopped")
