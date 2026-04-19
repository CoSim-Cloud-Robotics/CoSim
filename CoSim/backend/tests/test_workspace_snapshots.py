"""Tests for Workspace Snapshot Agent service layer and API.

TDD: These tests define the expected behaviour of workspace snapshots
before the implementation exists.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from co_sim.core import redis as redis_helpers


@pytest_asyncio.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_config_schema():
    """SnapshotConfig validates required fields."""
    from co_sim.services.workspace_snapshots import SnapshotConfig

    config = SnapshotConfig(
        workspace_id="ws-1",
        name="baseline-checkpoint",
        description="Initial working state",
        include_source=True,
        include_dependencies=True,
        include_data_refs=True,
    )
    assert config.workspace_id is not None
    assert config.name is not None
    assert config.include_source is True


@pytest.mark.asyncio
async def test_snapshot_metadata_schema():
    """SnapshotMetadata captures snapshot information."""
    from co_sim.services.workspace_snapshots import SnapshotMetadata

    metadata = SnapshotMetadata(
        snapshot_id="snap-abc",
        workspace_id="ws-1",
        name="v1.0-release",
        description="Release snapshot",
        created_at=1234567890.0,
        size_bytes=1024000,
        file_count=25,
    )
    assert metadata.snapshot_id.startswith("snap-")
    assert metadata.size_bytes > 0
    assert metadata.file_count > 0


# ---------------------------------------------------------------------------
# Snapshot creation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_snapshot(tmp_path):
    """Create a workspace snapshot with source files."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
    )

    # Setup workspace files
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "main.py").write_text("print('hello')")
    (workspace_dir / "utils.py").write_text("def helper(): pass")

    config = SnapshotConfig(
        workspace_id="ws-snap",
        name="test-snapshot",
        description="Test snapshot creation",
        include_source=True,
    )

    metadata = await create_snapshot(config, workspace_path=str(workspace_dir))

    assert metadata.snapshot_id is not None
    assert metadata.workspace_id == "ws-snap"
    assert metadata.name == "test-snapshot"
    assert metadata.file_count >= 2


@pytest.mark.asyncio
async def test_create_snapshot_with_dependencies(tmp_path):
    """Create snapshot including dependency lockfiles."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
    )

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "main.py").write_text("import numpy")
    (workspace_dir / "requirements.txt").write_text("numpy==1.24.0\npandas==2.0.0")

    config = SnapshotConfig(
        workspace_id="ws-deps",
        name="with-deps",
        include_source=True,
        include_dependencies=True,
    )

    metadata = await create_snapshot(config, workspace_path=str(workspace_dir))

    assert metadata.file_count >= 2  # main.py + requirements.txt


@pytest.mark.asyncio
async def test_create_snapshot_with_data_refs(tmp_path):
    """Create snapshot with data file references."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
    )

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "train.py").write_text("# training script")

    data_dir = workspace_dir / "data"
    data_dir.mkdir()
    (data_dir / "dataset.csv").write_text("col1,col2\n1,2\n3,4")

    config = SnapshotConfig(
        workspace_id="ws-data",
        name="with-data",
        include_source=True,
        include_data_refs=True,
    )

    metadata = await create_snapshot(config, workspace_path=str(workspace_dir))

    assert metadata.file_count >= 2


# ---------------------------------------------------------------------------
# Snapshot restoration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_snapshot(tmp_path):
    """Restore workspace from snapshot."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
        restore_snapshot,
    )

    # Create original workspace
    workspace_dir = tmp_path / "original"
    workspace_dir.mkdir()
    (workspace_dir / "code.py").write_text("original_code = True")

    # Create snapshot
    config = SnapshotConfig(
        workspace_id="ws-restore",
        name="backup",
        include_source=True,
    )
    metadata = await create_snapshot(config, workspace_path=str(workspace_dir))

    # Restore to new location
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()

    result = await restore_snapshot(
        metadata.snapshot_id,
        restore_path=str(restore_dir),
    )

    assert result["status"] == "restored"
    assert (restore_dir / "code.py").exists()
    assert (restore_dir / "code.py").read_text() == "original_code = True"


@pytest.mark.asyncio
async def test_restore_preserves_file_structure(tmp_path):
    """Restored snapshot preserves directory structure."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
        restore_snapshot,
    )

    # Create workspace with subdirectories
    workspace_dir = tmp_path / "original"
    workspace_dir.mkdir()

    src_dir = workspace_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("main")

    tests_dir = workspace_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("test")

    # Create and restore snapshot
    config = SnapshotConfig(
        workspace_id="ws-struct",
        name="structured",
        include_source=True,
    )
    metadata = await create_snapshot(config, workspace_path=str(workspace_dir))

    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()

    await restore_snapshot(metadata.snapshot_id, restore_path=str(restore_dir))

    assert (restore_dir / "src" / "main.py").exists()
    assert (restore_dir / "tests" / "test_main.py").exists()


# ---------------------------------------------------------------------------
# Snapshot listing and metadata tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_snapshots(tmp_path):
    """List all snapshots for a workspace."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
        list_snapshots,
    )

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "file.py").write_text("code")

    # Create multiple snapshots
    for i in range(3):
        config = SnapshotConfig(
            workspace_id="ws-list",
            name=f"snapshot-{i}",
            include_source=True,
        )
        await create_snapshot(config, workspace_path=str(workspace_dir))

    snapshots = await list_snapshots("ws-list")

    assert len(snapshots) == 3
    assert all(s["workspace_id"] == "ws-list" for s in snapshots)


@pytest.mark.asyncio
async def test_get_snapshot_metadata():
    """Get metadata for a specific snapshot."""
    from co_sim.services.workspace_snapshots import (
        get_snapshot_metadata,
        persist_snapshot_metadata,
        SnapshotMetadata,
    )

    metadata = SnapshotMetadata(
        snapshot_id="snap-meta",
        workspace_id="ws-meta",
        name="metadata-test",
        description="Testing metadata retrieval",
        created_at=1234567890.0,
        size_bytes=5000,
        file_count=10,
    )

    await persist_snapshot_metadata(metadata)

    retrieved = await get_snapshot_metadata("snap-meta")

    assert retrieved is not None
    assert retrieved["snapshot_id"] == "snap-meta"
    assert retrieved["name"] == "metadata-test"
    assert retrieved["file_count"] == 10


# ---------------------------------------------------------------------------
# Snapshot deletion tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_snapshot(tmp_path):
    """Delete a snapshot."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
        delete_snapshot,
        get_snapshot_metadata,
    )

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "file.py").write_text("code")

    config = SnapshotConfig(
        workspace_id="ws-delete",
        name="to-delete",
        include_source=True,
    )

    metadata = await create_snapshot(config, workspace_path=str(workspace_dir))
    snapshot_id = metadata.snapshot_id

    # Delete snapshot
    result = await delete_snapshot(snapshot_id)

    assert result["status"] == "deleted"
    assert result["snapshot_id"] == snapshot_id

    # Verify it's deleted
    deleted_metadata = await get_snapshot_metadata(snapshot_id)
    assert deleted_metadata is None


# ---------------------------------------------------------------------------
# Snapshot comparison tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compare_snapshots(tmp_path):
    """Compare two snapshots to see differences."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
        compare_snapshots,
    )

    # Create first workspace state
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "file1.py").write_text("version 1")

    config1 = SnapshotConfig(
        workspace_id="ws-compare",
        name="v1",
        include_source=True,
    )
    metadata1 = await create_snapshot(config1, workspace_path=str(workspace_dir))

    # Modify workspace
    (workspace_dir / "file1.py").write_text("version 2")
    (workspace_dir / "file2.py").write_text("new file")

    config2 = SnapshotConfig(
        workspace_id="ws-compare",
        name="v2",
        include_source=True,
    )
    metadata2 = await create_snapshot(config2, workspace_path=str(workspace_dir))

    # Compare snapshots
    diff = await compare_snapshots(metadata1.snapshot_id, metadata2.snapshot_id)

    assert "added" in diff
    assert "modified" in diff
    assert "deleted" in diff
    assert len(diff["added"]) >= 1  # file2.py was added
    assert len(diff["modified"]) >= 1  # file1.py was modified


# ---------------------------------------------------------------------------
# State persistence in Redis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_snapshot_metadata():
    """Snapshot metadata is persisted to Redis."""
    from co_sim.services.workspace_snapshots import (
        SnapshotMetadata,
        persist_snapshot_metadata,
        get_snapshot_metadata,
    )

    metadata = SnapshotMetadata(
        snapshot_id="snap-persist",
        workspace_id="ws-persist",
        name="persist-test",
        description="Test persistence",
        created_at=1234567890.0,
        size_bytes=1000,
        file_count=5,
    )

    await persist_snapshot_metadata(metadata)

    retrieved = await get_snapshot_metadata("snap-persist")

    assert retrieved is not None
    assert retrieved["workspace_id"] == "ws-persist"
    assert retrieved["size_bytes"] == 1000


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_workflow_end_to_end(tmp_path):
    """Complete workflow: create, list, restore, delete."""
    from co_sim.services.workspace_snapshots import (
        SnapshotConfig,
        create_snapshot,
        list_snapshots,
        restore_snapshot,
        delete_snapshot,
    )

    # Setup workspace
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "main.py").write_text("def main(): pass")
    (workspace_dir / "utils.py").write_text("def helper(): pass")

    # Create snapshot
    config = SnapshotConfig(
        workspace_id="ws-e2e",
        name="e2e-snapshot",
        description="End-to-end test",
        include_source=True,
    )

    metadata = await create_snapshot(config, workspace_path=str(workspace_dir))
    assert metadata.file_count >= 2

    # List snapshots
    snapshots = await list_snapshots("ws-e2e")
    assert len(snapshots) == 1

    # Restore snapshot
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()

    restore_result = await restore_snapshot(
        metadata.snapshot_id,
        restore_path=str(restore_dir),
    )
    assert restore_result["status"] == "restored"
    assert (restore_dir / "main.py").exists()

    # Delete snapshot
    delete_result = await delete_snapshot(metadata.snapshot_id)
    assert delete_result["status"] == "deleted"

    # Verify deletion
    snapshots_after = await list_snapshots("ws-e2e")
    assert len(snapshots_after) == 0
