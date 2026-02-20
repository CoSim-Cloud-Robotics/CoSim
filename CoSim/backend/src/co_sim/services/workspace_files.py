from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.models.workspace_file import WorkspaceFile
from co_sim.schemas.workspace_file import WorkspaceFileRead, WorkspaceFileUpsert
from co_sim.services import workspace_fs
from co_sim.core.config import settings


async def list_workspace_files(session: AsyncSession, workspace_id: UUID) -> list[WorkspaceFileRead]:
    result = await session.execute(
        select(WorkspaceFile).where(WorkspaceFile.workspace_id == workspace_id).order_by(WorkspaceFile.path)
    )
    files = result.scalars().all()
    return [WorkspaceFileRead.model_validate(file) for file in files]


async def get_workspace_file(session: AsyncSession, workspace_id: UUID, path: str) -> WorkspaceFile | None:
    result = await session.execute(
        select(WorkspaceFile).where(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.path == path,
        )
    )
    return result.scalar_one_or_none()


async def upsert_workspace_file(
    session: AsyncSession, workspace_id: UUID, payload: WorkspaceFileUpsert
) -> WorkspaceFileRead:
    workspace_file = await get_workspace_file(session, workspace_id, payload.path)

    if workspace_file is None:
        workspace_file = WorkspaceFile(
            workspace_id=workspace_id,
            path=payload.path,
            content=payload.content,
            language=payload.language,
        )
        session.add(workspace_file)
    else:
        workspace_file.content = payload.content
        workspace_file.language = payload.language

    await session.commit()
    await session.refresh(workspace_file)

    if settings.workspace_fs_enabled:
        try:
            await workspace_fs.write_file(workspace_id, payload.path, payload.content)
        except Exception:  # pragma: no cover - best effort sync
            pass

    return WorkspaceFileRead.model_validate(workspace_file)


async def delete_workspace_path(
    session: AsyncSession,
    workspace_id: UUID,
    path: str,
    recursive: bool = False,
) -> int:
    if recursive:
        condition = (WorkspaceFile.path == path) | (WorkspaceFile.path.like(f"{path}/%"))
    else:
        condition = WorkspaceFile.path == path

    result = await session.execute(
        delete(WorkspaceFile).where(
            WorkspaceFile.workspace_id == workspace_id,
            condition,
        )
    )
    await session.commit()

    if settings.workspace_fs_enabled:
        try:
            await workspace_fs.delete_path(workspace_id, path)
        except Exception:  # pragma: no cover - best effort sync
            pass

    return result.rowcount or 0


async def rename_workspace_path(
    session: AsyncSession,
    workspace_id: UUID,
    source_path: str,
    destination_path: str,
) -> list[WorkspaceFileRead]:
    result = await session.execute(
        select(WorkspaceFile).where(
            WorkspaceFile.workspace_id == workspace_id,
            (WorkspaceFile.path == source_path) | (WorkspaceFile.path.like(f"{source_path}/%")),
        )
    )
    files = result.scalars().all()
    if not files:
        return []

    source_prefix = f"{source_path}/"
    dest_prefix = f"{destination_path}/"
    updated_paths = []
    current_paths = {file.path for file in files}
    for file in files:
        if file.path == source_path:
            updated_paths.append(destination_path)
        else:
            updated_paths.append(file.path.replace(source_prefix, dest_prefix, 1))

    collision_result = await session.execute(
        select(WorkspaceFile.path).where(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.path.in_(updated_paths),
        )
    )
    collisions = {row[0] for row in collision_result.all()} - current_paths
    if collisions:
        raise ValueError(f"Destination path(s) already exist: {sorted(collisions)}")

    for file, updated_path in zip(files, updated_paths):
        file.path = updated_path

    await session.commit()

    if settings.workspace_fs_enabled:
        try:
            await workspace_fs.rename_path(workspace_id, source_path, destination_path)
        except Exception:  # pragma: no cover - best effort sync
            pass

    return [WorkspaceFileRead.model_validate(file) for file in files]
