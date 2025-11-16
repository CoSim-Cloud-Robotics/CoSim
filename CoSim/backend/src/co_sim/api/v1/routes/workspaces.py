from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.api.dependencies import get_current_user
from co_sim.db.session import get_db
from co_sim.models.user import User
from co_sim.schemas.workspace import WorkspaceCreate, WorkspaceRead, WorkspaceUpdate
from co_sim.schemas.workspace_file import WorkspaceFileRead, WorkspaceFileUpsert
from co_sim.services import workspaces as workspace_service
from co_sim.services import workspace_files as workspace_file_service
from co_sim.typing import Annotated

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRead:
    _ = current_user
    return await workspace_service.create_workspace(session, payload)


@router.get("", response_model=List[WorkspaceRead])
async def list_workspaces(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    project_id: UUID | None = Query(default=None),
) -> list[WorkspaceRead]:
    _ = current_user
    return await workspace_service.list_workspaces(session, project_id=project_id)


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRead:
    _ = current_user
    workspace = await workspace_service.get_workspace(session, workspace_id)
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return WorkspaceRead.model_validate(workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRead:
    _ = current_user
    workspace = await workspace_service.get_workspace(session, workspace_id)
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return await workspace_service.update_workspace(session, workspace, payload)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _ = current_user
    await workspace_service.delete_workspace(session, workspace_id)


@router.get("/{workspace_id}/files", response_model=List[WorkspaceFileRead])
async def list_workspace_files(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkspaceFileRead]:
    _ = current_user
    return await workspace_file_service.list_workspace_files(session, workspace_id)


@router.put("/{workspace_id}/files", response_model=WorkspaceFileRead)
async def upsert_workspace_file(
    workspace_id: UUID,
    payload: WorkspaceFileUpsert,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceFileRead:
    _ = current_user
    return await workspace_file_service.upsert_workspace_file(session, workspace_id, payload)
