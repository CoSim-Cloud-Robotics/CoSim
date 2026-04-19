"""Workspace Snapshot Agent — create, restore, and manage workspace snapshots.

Provides:
- SnapshotConfig / SnapshotMetadata schemas
- create_snapshot() — capture workspace state (source + deps + data refs)
- restore_snapshot() — restore workspace from snapshot
- list_snapshots() / get_snapshot_metadata() — snapshot discovery
- delete_snapshot() — snapshot cleanup
- compare_snapshots() — diff between snapshots
- persist_snapshot_metadata() — Redis state
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from co_sim.core.redis import get_redis


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SnapshotConfig(BaseModel):
    """Configuration for creating a workspace snapshot."""

    workspace_id: str
    name: str
    description: str = ""
    include_source: bool = True
    include_dependencies: bool = False
    include_data_refs: bool = False


class SnapshotMetadata(BaseModel):
    """Metadata for a workspace snapshot."""

    snapshot_id: str
    workspace_id: str
    name: str
    description: str = ""
    created_at: float = Field(default_factory=time.time)
    size_bytes: int
    file_count: int


# ---------------------------------------------------------------------------
# Snapshot Creation
# ---------------------------------------------------------------------------

async def create_snapshot(
    config: SnapshotConfig,
    workspace_path: str,
    snapshot_storage: str = "/tmp/cosim/snapshots",
) -> SnapshotMetadata:
    """Create a workspace snapshot.

    Args:
        config: Snapshot configuration
        workspace_path: Path to workspace directory
        snapshot_storage: Root directory for snapshot storage

    Returns:
        SnapshotMetadata with snapshot information
    """
    workspace_dir = Path(workspace_path)

    if not workspace_dir.exists():
        raise FileNotFoundError(f"Workspace path not found: {workspace_path}")

    # Generate snapshot ID
    snapshot_id = f"snap-{uuid.uuid4().hex[:8]}"

    # Create snapshot directory
    snapshot_dir = Path(snapshot_storage) / config.workspace_id / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Copy files based on configuration
    file_count = 0
    total_size = 0

    if config.include_source:
        # Copy all source files
        for file_path in workspace_dir.rglob("*"):
            if file_path.is_file():
                # Skip certain files
                if _should_exclude_file(file_path):
                    continue

                # Compute relative path
                rel_path = file_path.relative_to(workspace_dir)
                dest_path = snapshot_dir / rel_path

                # Create parent directories
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Copy file
                shutil.copy2(file_path, dest_path)

                file_count += 1
                total_size += file_path.stat().st_size

    # Create metadata
    metadata = SnapshotMetadata(
        snapshot_id=snapshot_id,
        workspace_id=config.workspace_id,
        name=config.name,
        description=config.description,
        created_at=time.time(),
        size_bytes=total_size,
        file_count=file_count,
    )

    # Persist metadata
    await persist_snapshot_metadata(metadata)

    return metadata


def _should_exclude_file(file_path: Path) -> bool:
    """Check if file should be excluded from snapshot."""
    exclude_patterns = [
        "__pycache__",
        ".pyc",
        ".pyo",
        ".git",
        ".DS_Store",
        "node_modules",
        ".pytest_cache",
    ]

    path_str = str(file_path)
    return any(pattern in path_str for pattern in exclude_patterns)


# ---------------------------------------------------------------------------
# Snapshot Restoration
# ---------------------------------------------------------------------------

async def restore_snapshot(
    snapshot_id: str,
    restore_path: str,
    snapshot_storage: str = "/tmp/cosim/snapshots",
) -> Dict[str, Any]:
    """Restore workspace from snapshot.

    Args:
        snapshot_id: Snapshot identifier
        restore_path: Path to restore workspace to
        snapshot_storage: Root directory for snapshot storage

    Returns:
        Restoration status
    """
    # Get snapshot metadata
    metadata = await get_snapshot_metadata(snapshot_id)

    if metadata is None:
        raise ValueError(f"Snapshot {snapshot_id} not found")

    # Find snapshot directory
    snapshot_dir = Path(snapshot_storage) / metadata["workspace_id"] / snapshot_id

    if not snapshot_dir.exists():
        raise FileNotFoundError(f"Snapshot storage not found: {snapshot_dir}")

    restore_dir = Path(restore_path)

    # Copy all files from snapshot to restore location
    for file_path in snapshot_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(snapshot_dir)
            dest_path = restore_dir / rel_path

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_path)

    return {
        "status": "restored",
        "snapshot_id": snapshot_id,
        "restore_path": str(restore_dir),
        "file_count": metadata["file_count"],
    }


# ---------------------------------------------------------------------------
# Snapshot Listing and Discovery
# ---------------------------------------------------------------------------

async def list_snapshots(workspace_id: str) -> List[Dict[str, Any]]:
    """List all snapshots for a workspace.

    Args:
        workspace_id: Workspace identifier

    Returns:
        List of snapshot metadata dictionaries
    """
    redis = await get_redis()
    key = f"snapshots:{workspace_id}"

    snapshot_ids = await redis.smembers(key)

    snapshots = []
    for snapshot_id in snapshot_ids:
        metadata = await get_snapshot_metadata(snapshot_id)
        if metadata:
            snapshots.append(metadata)

    # Sort by creation time (newest first)
    snapshots.sort(key=lambda x: x["created_at"], reverse=True)

    return snapshots


async def get_snapshot_metadata(snapshot_id: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific snapshot.

    Args:
        snapshot_id: Snapshot identifier

    Returns:
        Snapshot metadata dictionary, or None if not found
    """
    redis = await get_redis()
    key = f"snapshot:{snapshot_id}:metadata"

    data = await redis.get(key)
    if data is None:
        return None

    return json.loads(data)


# ---------------------------------------------------------------------------
# Snapshot Deletion
# ---------------------------------------------------------------------------

async def delete_snapshot(
    snapshot_id: str,
    snapshot_storage: str = "/tmp/cosim/snapshots",
) -> Dict[str, Any]:
    """Delete a snapshot.

    Args:
        snapshot_id: Snapshot identifier
        snapshot_storage: Root directory for snapshot storage

    Returns:
        Deletion status
    """
    # Get snapshot metadata
    metadata = await get_snapshot_metadata(snapshot_id)

    if metadata is None:
        raise ValueError(f"Snapshot {snapshot_id} not found")

    # Remove snapshot files
    snapshot_dir = Path(snapshot_storage) / metadata["workspace_id"] / snapshot_id

    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)

    # Remove metadata from Redis
    redis = await get_redis()

    await redis.delete(f"snapshot:{snapshot_id}:metadata")
    await redis.srem(f"snapshots:{metadata['workspace_id']}", snapshot_id)

    return {
        "status": "deleted",
        "snapshot_id": snapshot_id,
    }


# ---------------------------------------------------------------------------
# Snapshot Comparison
# ---------------------------------------------------------------------------

async def compare_snapshots(
    snapshot_id_1: str,
    snapshot_id_2: str,
    snapshot_storage: str = "/tmp/cosim/snapshots",
) -> Dict[str, List[str]]:
    """Compare two snapshots to see differences.

    Args:
        snapshot_id_1: First snapshot ID
        snapshot_id_2: Second snapshot ID
        snapshot_storage: Root directory for snapshot storage

    Returns:
        Dictionary with added, modified, and deleted files
    """
    # Get metadata for both snapshots
    metadata1 = await get_snapshot_metadata(snapshot_id_1)
    metadata2 = await get_snapshot_metadata(snapshot_id_2)

    if metadata1 is None or metadata2 is None:
        raise ValueError("One or both snapshots not found")

    # Get snapshot directories
    snapshot_dir1 = Path(snapshot_storage) / metadata1["workspace_id"] / snapshot_id_1
    snapshot_dir2 = Path(snapshot_storage) / metadata2["workspace_id"] / snapshot_id_2

    # Get file lists
    files1 = {
        str(f.relative_to(snapshot_dir1)): _file_hash(f)
        for f in snapshot_dir1.rglob("*")
        if f.is_file()
    }

    files2 = {
        str(f.relative_to(snapshot_dir2)): _file_hash(f)
        for f in snapshot_dir2.rglob("*")
        if f.is_file()
    }

    # Compute differences
    added = [f for f in files2 if f not in files1]
    deleted = [f for f in files1 if f not in files2]
    modified = [
        f for f in files1
        if f in files2 and files1[f] != files2[f]
    ]

    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
    }


def _file_hash(file_path: Path) -> str:
    """Compute hash of file contents."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        hasher.update(f.read())
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# State Persistence
# ---------------------------------------------------------------------------

async def persist_snapshot_metadata(metadata: SnapshotMetadata):
    """Persist snapshot metadata to Redis.

    Args:
        metadata: Snapshot metadata to persist
    """
    redis = await get_redis()

    # Store metadata
    key = f"snapshot:{metadata.snapshot_id}:metadata"
    await redis.set(key, json.dumps(metadata.model_dump()))

    # Add to workspace's snapshot set
    await redis.sadd(f"snapshots:{metadata.workspace_id}", metadata.snapshot_id)
