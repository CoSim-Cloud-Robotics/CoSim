from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.core.config import settings
from co_sim.models.workspace_file import WorkspaceFile


class WorkspacePathError(ValueError):
    pass


def _normalize_relative_path(path: str) -> PurePosixPath:
    cleaned = path.strip()
    if not cleaned:
        raise WorkspacePathError("Path is required")
    posix = PurePosixPath(cleaned)
    if posix.is_absolute():
        posix = posix.relative_to("/")
    if ".." in posix.parts:
        raise WorkspacePathError("Invalid path traversal")
    return posix


def _workspace_root(workspace_id: UUID | str | os.PathLike[str]) -> Path:
    return Path(settings.workspace_root) / str(workspace_id)


def resolve_workspace_path(workspace_id: UUID | str | os.PathLike[str], path: str) -> Path:
    relative = _normalize_relative_path(path)
    return _workspace_root(workspace_id) / relative


async def ensure_workspace_dir(workspace_id: UUID | str | os.PathLike[str]) -> Path:
    root = _workspace_root(workspace_id)
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    return root


async def write_file(workspace_id: UUID | str | os.PathLike[str], path: str, content: str) -> None:
    root = await ensure_workspace_dir(workspace_id)
    relative = _normalize_relative_path(path)

    def _write() -> None:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    await asyncio.to_thread(_write)


async def delete_path(workspace_id: UUID | str | os.PathLike[str], path: str) -> None:
    root = await ensure_workspace_dir(workspace_id)
    relative = _normalize_relative_path(path)

    def _delete() -> None:
        target = root / relative
        if not target.exists():
            return
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    await asyncio.to_thread(_delete)


async def rename_path(
    workspace_id: UUID | str | os.PathLike[str],
    source: str,
    destination: str,
) -> None:
    root = await ensure_workspace_dir(workspace_id)
    source_relative = _normalize_relative_path(source)
    destination_relative = _normalize_relative_path(destination)

    def _rename() -> None:
        source_path = root / source_relative
        destination_path = root / destination_relative
        if not source_path.exists():
            return
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.rename(destination_path)

    await asyncio.to_thread(_rename)


async def sync_from_db(session: AsyncSession, workspace_id: UUID | str) -> None:
    root = await ensure_workspace_dir(workspace_id)
    result = await session.execute(
        select(WorkspaceFile).where(WorkspaceFile.workspace_id == workspace_id).order_by(WorkspaceFile.path)
    )
    files: Iterable[WorkspaceFile] = result.scalars().all()

    def _write_all() -> None:
        for file in files:
            relative = _normalize_relative_path(file.path)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content or "", encoding="utf-8")

    await asyncio.to_thread(_write_all)
