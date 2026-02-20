from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.api.dependencies import get_current_user
from co_sim.db.session import get_db
from co_sim.models.user import User
from co_sim.schemas.git import GitAddRequest, GitCommitRequest, GitDiffResponse, GitStatusResponse
from co_sim.schemas.workspace import WorkspaceCreate, WorkspaceRead, WorkspaceUpdate
from co_sim.schemas.workspace_file import WorkspaceFileRead, WorkspaceFileRename, WorkspaceFileUpsert
from co_sim.services import workspaces as workspace_service
from co_sim.services import workspace_files as workspace_file_service
from co_sim.services import workspace_git as workspace_git_service
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


@router.delete("/{workspace_id}/files", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_path(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    path: str = Query(..., min_length=1, max_length=512),
    recursive: bool = Query(default=False),
) -> None:
    _ = current_user
    await workspace_file_service.delete_workspace_path(session, workspace_id, path, recursive=recursive)


@router.post("/{workspace_id}/files/rename", response_model=List[WorkspaceFileRead])
async def rename_workspace_path(
    workspace_id: UUID,
    payload: WorkspaceFileRename,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkspaceFileRead]:
    _ = current_user
    try:
        return await workspace_file_service.rename_workspace_path(
            session,
            workspace_id,
            payload.source_path,
            payload.destination_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{workspace_id}/git/status", response_model=GitStatusResponse)
async def get_git_status(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GitStatusResponse:
    _ = current_user
    try:
        entries = await workspace_git_service.git_status(session, workspace_id)
        return GitStatusResponse(entries=[e.__dict__ for e in entries])
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{workspace_id}/git/add", status_code=status.HTTP_202_ACCEPTED)
async def add_git_paths(
    workspace_id: UUID,
    payload: GitAddRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    _ = current_user
    try:
        await workspace_git_service.git_add(session, workspace_id, payload.paths)
        return {"status": "staged"}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{workspace_id}/git/commit", status_code=status.HTTP_201_CREATED)
async def commit_git(
    workspace_id: UUID,
    payload: GitCommitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    _ = current_user
    try:
        output = await workspace_git_service.git_commit(session, workspace_id, payload.message)
        return {"status": "committed", "output": output.strip()}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{workspace_id}/git/diff", response_model=GitDiffResponse)
async def get_git_diff(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    staged: bool = Query(default=False),
    path: str | None = Query(default=None),
) -> GitDiffResponse:
    _ = current_user
    try:
        diff = await workspace_git_service.git_diff(session, workspace_id, staged=staged, path=path)
        return GitDiffResponse(diff=diff)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
