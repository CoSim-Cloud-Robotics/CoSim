"""Tests for workspace file persistence — verifying the full CRUD cycle.

TDD: Ensures files round-trip through the service layer using an
in-memory SQLite backend (no Postgres needed).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import String, Text, UniqueConstraint, DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from co_sim.schemas.workspace_file import WorkspaceFileUpsert, WorkspaceFileRename
from co_sim.services import workspace_files as wf_service


# ---------------------------------------------------------------------------
# SQLite-compatible mirror of WorkspaceFile for testing
# ---------------------------------------------------------------------------

class _TestBase(DeclarativeBase):
    pass


class _TestWorkspaceFile(_TestBase):
    __tablename__ = "workspace_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("workspace_id", "path", name="uq_workspace_file_path"),)


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite async session for testing.

    We patch the WorkspaceFile model reference inside the service module
    to use our SQLite-compatible test model.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        # Patch the model + FS sync for isolation
        with patch.object(wf_service, "WorkspaceFile", _TestWorkspaceFile), \
             patch.object(wf_service, "workspace_fs", AsyncMock()), \
             patch.object(wf_service.settings, "workspace_fs_enabled", False):
            yield session

    await engine.dispose()


# Use a consistent workspace_id across tests — as a string for SQLite compat.
# Pydantic will coerce it to UUID in WorkspaceFileRead, so comparisons use str().
WS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_creates_new_file(db_session: AsyncSession):
    """Upserting a file that doesn't exist creates it."""
    payload = WorkspaceFileUpsert(path="src/main.py", content="print('hello')", language="python")
    result = await wf_service.upsert_workspace_file(db_session, WS_ID, payload)

    assert result.path == "src/main.py"
    assert result.content == "print('hello')"
    assert result.language == "python"
    assert str(result.workspace_id) == WS_ID


@pytest.mark.asyncio
async def test_upsert_updates_existing_file(db_session: AsyncSession):
    """Upserting an existing path updates content and language."""
    payload1 = WorkspaceFileUpsert(path="src/main.py", content="v1", language="python")
    await wf_service.upsert_workspace_file(db_session, WS_ID, payload1)

    payload2 = WorkspaceFileUpsert(path="src/main.py", content="v2", language="python")
    result = await wf_service.upsert_workspace_file(db_session, WS_ID, payload2)

    assert result.content == "v2"

    # Only one file should exist
    files = await wf_service.list_workspace_files(db_session, WS_ID)
    assert len(files) == 1


@pytest.mark.asyncio
async def test_list_workspace_files_ordered(db_session: AsyncSession):
    """Files are returned sorted by path."""
    for path in ["z.py", "a.py", "m.py"]:
        await wf_service.upsert_workspace_file(
            db_session, WS_ID, WorkspaceFileUpsert(path=path, content="", language="python")
        )

    files = await wf_service.list_workspace_files(db_session, WS_ID)
    paths = [f.path for f in files]
    assert paths == ["a.py", "m.py", "z.py"]


@pytest.mark.asyncio
async def test_get_workspace_file(db_session: AsyncSession):
    """get_workspace_file returns the file or None."""
    await wf_service.upsert_workspace_file(
        db_session, WS_ID, WorkspaceFileUpsert(path="found.py", content="x", language="python")
    )

    found = await wf_service.get_workspace_file(db_session, WS_ID, "found.py")
    assert found is not None
    assert found.content == "x"

    missing = await wf_service.get_workspace_file(db_session, WS_ID, "missing.py")
    assert missing is None


@pytest.mark.asyncio
async def test_delete_single_file(db_session: AsyncSession):
    """Deleting a single path removes exactly one file."""
    for path in ["a.py", "b.py"]:
        await wf_service.upsert_workspace_file(
            db_session, WS_ID, WorkspaceFileUpsert(path=path, content="", language="python")
        )

    deleted = await wf_service.delete_workspace_path(db_session, WS_ID, "a.py")
    assert deleted == 1

    remaining = await wf_service.list_workspace_files(db_session, WS_ID)
    assert len(remaining) == 1
    assert remaining[0].path == "b.py"


@pytest.mark.asyncio
async def test_delete_recursive(db_session: AsyncSession):
    """Recursive delete removes a directory and all children."""
    for path in ["src/a.py", "src/sub/b.py", "README.md"]:
        await wf_service.upsert_workspace_file(
            db_session, WS_ID, WorkspaceFileUpsert(path=path, content="", language="python")
        )

    deleted = await wf_service.delete_workspace_path(db_session, WS_ID, "src", recursive=True)
    assert deleted == 2

    remaining = await wf_service.list_workspace_files(db_session, WS_ID)
    assert len(remaining) == 1
    assert remaining[0].path == "README.md"


@pytest.mark.asyncio
async def test_rename_single_file(db_session: AsyncSession):
    """Renaming a file updates its path."""
    await wf_service.upsert_workspace_file(
        db_session, WS_ID, WorkspaceFileUpsert(path="old.py", content="data", language="python")
    )

    renamed = await wf_service.rename_workspace_path(db_session, WS_ID, "old.py", "new.py")
    assert len(renamed) == 1
    assert renamed[0].path == "new.py"
    assert renamed[0].content == "data"


@pytest.mark.asyncio
async def test_rename_directory(db_session: AsyncSession):
    """Renaming a directory renames all children."""
    for path in ["src/a.py", "src/sub/b.py"]:
        await wf_service.upsert_workspace_file(
            db_session, WS_ID, WorkspaceFileUpsert(path=path, content="", language="python")
        )

    renamed = await wf_service.rename_workspace_path(db_session, WS_ID, "src", "lib")
    paths = sorted(f.path for f in renamed)
    assert paths == ["lib/a.py", "lib/sub/b.py"]


@pytest.mark.asyncio
async def test_rename_collision_raises(db_session: AsyncSession):
    """Renaming to an existing path raises ValueError."""
    for path in ["a.py", "b.py"]:
        await wf_service.upsert_workspace_file(
            db_session, WS_ID, WorkspaceFileUpsert(path=path, content="", language="python")
        )

    with pytest.raises(ValueError, match="already exist"):
        await wf_service.rename_workspace_path(db_session, WS_ID, "a.py", "b.py")


@pytest.mark.asyncio
async def test_empty_workspace_returns_empty_list(db_session: AsyncSession):
    """Listing files from a workspace with no files returns []."""
    files = await wf_service.list_workspace_files(db_session, WS_ID)
    assert files == []
