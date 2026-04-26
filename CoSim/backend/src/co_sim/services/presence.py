"""Workspace presence service.

Tracks who is currently active in each workspace so the frontend can render
collaborator avatars in the IDE shell. This complements the in-editor Yjs
awareness (cursors/selections inside Monaco) by providing a workspace-wide
list that survives across documents and tabs.

Persistence model
-----------------
- ``cosim:presence:<workspace_id>`` — Redis hash mapping user_id -> JSON record
- ``cosim:channel:cosim:presence:<workspace_id>`` — pub/sub for live updates

Each record stores a ``last_seen`` epoch so callers can filter inactive users
even before Redis evicts them.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Optional

from co_sim.core.redis import get_redis, publish

_PRESENCE_KEY_PREFIX = "cosim:presence"
_PRESENCE_TTL_SECONDS = 300
_DEFAULT_ACTIVE_WINDOW = 90


def _presence_key(workspace_id: str) -> str:
    return f"{_PRESENCE_KEY_PREFIX}:{workspace_id}"


def presence_channel(workspace_id: str) -> str:
    """Return the pub/sub channel name for a workspace's presence updates."""

    return f"{_PRESENCE_KEY_PREFIX}:{workspace_id}"


@dataclass
class PresenceRecord:
    workspace_id: str
    user_id: str
    name: str
    color: str
    avatar_url: Optional[str] = None
    active_file: Optional[str] = None
    last_seen: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PresenceRecord":
        return cls(
            workspace_id=str(data.get("workspace_id", "")),
            user_id=str(data.get("user_id", "")),
            name=str(data.get("name", "")),
            color=str(data.get("color", "")),
            avatar_url=data.get("avatar_url") if data.get("avatar_url") else None,  # type: ignore[arg-type]
            active_file=data.get("active_file") if data.get("active_file") else None,  # type: ignore[arg-type]
            last_seen=float(data.get("last_seen", 0.0)),
        )


async def register_presence(
    *,
    workspace_id: str,
    user_id: str,
    name: str,
    color: str,
    avatar_url: Optional[str] = None,
    active_file: Optional[str] = None,
) -> PresenceRecord:
    """Register or refresh a user's presence in a workspace."""

    record = PresenceRecord(
        workspace_id=workspace_id,
        user_id=user_id,
        name=name,
        color=color,
        avatar_url=avatar_url,
        active_file=active_file,
        last_seen=time.time(),
    )
    redis = await get_redis()
    key = _presence_key(workspace_id)
    await redis.hset(key, user_id, json.dumps(record.to_dict()))
    await redis.expire(key, _PRESENCE_TTL_SECONDS)
    await publish(
        presence_channel(workspace_id),
        json.dumps({"action": "register", **record.to_dict()}),
    )
    return record


async def heartbeat_presence(
    *,
    workspace_id: str,
    user_id: str,
    active_file: Optional[str] = None,
) -> Optional[PresenceRecord]:
    """Refresh ``last_seen`` (and optionally ``active_file``) for an existing user.

    Returns ``None`` if the user has not previously registered.
    """

    redis = await get_redis()
    key = _presence_key(workspace_id)
    raw = await redis.hget(key, user_id)
    if raw is None:
        return None
    payload = json.loads(raw)
    payload["last_seen"] = time.time()
    if active_file is not None:
        payload["active_file"] = active_file
    await redis.hset(key, user_id, json.dumps(payload))
    await redis.expire(key, _PRESENCE_TTL_SECONDS)
    return PresenceRecord.from_dict(payload)


async def list_presence(
    workspace_id: str,
    *,
    active_within_seconds: int = _DEFAULT_ACTIVE_WINDOW,
) -> list[PresenceRecord]:
    """Return active presence records for a workspace.

    Records older than ``active_within_seconds`` are filtered out so the UI
    doesn't keep ghost avatars even if Redis hasn't expired the key yet.
    """

    redis = await get_redis()
    key = _presence_key(workspace_id)
    raw_entries = await redis.hgetall(key)
    if not raw_entries:
        return []

    cutoff = time.time() - active_within_seconds
    active: list[PresenceRecord] = []
    stale_user_ids: list[str] = []
    for user_id, raw in raw_entries.items():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            stale_user_ids.append(user_id)
            continue
        record = PresenceRecord.from_dict(payload)
        if record.last_seen < cutoff:
            stale_user_ids.append(user_id)
            continue
        active.append(record)

    if stale_user_ids:
        await redis.hdel(key, *stale_user_ids)

    active.sort(key=lambda r: r.user_id)
    return active


async def remove_presence(*, workspace_id: str, user_id: str) -> bool:
    """Remove a user's presence and publish a leave event."""

    redis = await get_redis()
    key = _presence_key(workspace_id)
    removed = await redis.hdel(key, user_id)
    if removed:
        await publish(
            presence_channel(workspace_id),
            json.dumps(
                {
                    "action": "remove",
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                }
            ),
        )
    return bool(removed)


async def remove_workspace(workspace_id: str) -> int:
    """Drop every presence entry for a workspace; returns number removed."""

    redis = await get_redis()
    key = _presence_key(workspace_id)
    raw_entries = await redis.hgetall(key)
    count = len(raw_entries)
    if count:
        await redis.delete(key)
        await publish(
            presence_channel(workspace_id),
            json.dumps({"action": "clear", "workspace_id": workspace_id}),
        )
    return count
