"""Shared sim-control service.

Backs a CRDT-style ``sim-control.json`` document so collaborators can jointly
start/stop/reset/seed simulations from any client. The document is persisted
in Redis and replicated to listeners via pub/sub.

Convergence model
-----------------
- A monotonic ``version`` counter increments per applied command (atomic via
  Redis ``INCR``) — this acts as the Lamport-style timestamp that lets clients
  ignore stale updates and resolve conflicting writes.
- Each command is appended to a bounded history list keyed by workspace.
- Each command is published on ``cosim:sim-control:<workspace_id>`` so any Yjs
  / WebSocket subscriber can reflect the change.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from co_sim.core.redis import get_redis, publish

_STATE_KEY_PREFIX = "cosim:sim-control:state"
_VERSION_KEY_PREFIX = "cosim:sim-control:version"
_HISTORY_KEY_PREFIX = "cosim:sim-control:history"
_HISTORY_MAX = 50

VALID_COMMANDS = ("start", "stop", "reset", "seed", "update_params", "pause", "resume")
_RUNTIME_PARAM_KEYS = ("frame", "time", "step", "elapsed")


def _state_key(workspace_id: str) -> str:
    return f"{_STATE_KEY_PREFIX}:{workspace_id}"


def _version_key(workspace_id: str) -> str:
    return f"{_VERSION_KEY_PREFIX}:{workspace_id}"


def _history_key(workspace_id: str) -> str:
    return f"{_HISTORY_KEY_PREFIX}:{workspace_id}"


def sim_control_channel(workspace_id: str) -> str:
    """Return the pub/sub channel name for sim-control updates."""

    return f"cosim:sim-control:{workspace_id}"


@dataclass
class SimControlState:
    workspace_id: str
    status: str = "idle"
    engine: Optional[str] = None
    seed: Optional[int] = None
    params: dict[str, Any] = field(default_factory=dict)
    version: int = 0
    last_actor: Optional[str] = None
    last_command: Optional[str] = None
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimControlState":
        return cls(
            workspace_id=str(data.get("workspace_id", "")),
            status=str(data.get("status", "idle")),
            engine=data.get("engine"),
            seed=data.get("seed"),
            params=dict(data.get("params") or {}),
            version=int(data.get("version", 0)),
            last_actor=data.get("last_actor"),
            last_command=data.get("last_command"),
            updated_at=float(data.get("updated_at", 0.0)),
        )


@dataclass
class SimControlHistoryEntry:
    workspace_id: str
    version: int
    command: str
    actor: str
    seed: Optional[int]
    params: dict[str, Any]
    status: str
    timestamp: float


async def _load_state(workspace_id: str) -> SimControlState:
    redis = await get_redis()
    raw = await redis.get(_state_key(workspace_id))
    if not raw:
        return SimControlState(workspace_id=workspace_id)
    return SimControlState.from_dict(json.loads(raw))


async def _save_state(state: SimControlState) -> None:
    redis = await get_redis()
    await redis.set(_state_key(state.workspace_id), json.dumps(state.to_dict()))


async def _append_history(entry: SimControlHistoryEntry) -> None:
    redis = await get_redis()
    key = _history_key(entry.workspace_id)
    await redis.rpush(key, json.dumps(asdict(entry)))
    await redis.ltrim(key, -_HISTORY_MAX, -1)


async def _next_version(workspace_id: str) -> int:
    redis = await get_redis()
    return int(await redis.incr(_version_key(workspace_id)))


async def get_state(*, workspace_id: str) -> SimControlState:
    """Return the current sim-control state (default if uninitialized)."""

    return await _load_state(workspace_id)


async def initialize_state(
    *,
    workspace_id: str,
    engine: Optional[str] = None,
    seed: Optional[int] = None,
    params: Optional[dict[str, Any]] = None,
) -> SimControlState:
    """Seed initial sim-control values; bumps version and notifies subscribers."""

    state = await _load_state(workspace_id)
    state.engine = engine if engine is not None else state.engine
    state.seed = seed if seed is not None else state.seed
    if params:
        state.params.update(params)
    state.version = await _next_version(workspace_id)
    state.updated_at = time.time()
    state.last_command = "initialize"
    await _save_state(state)
    await publish(
        sim_control_channel(workspace_id),
        json.dumps({"command": "initialize", "actor": "system", **state.to_dict()}),
    )
    return state


async def apply_command(
    *,
    workspace_id: str,
    command: str,
    actor: str,
    seed: Optional[int] = None,
    params: Optional[dict[str, Any]] = None,
) -> SimControlState:
    """Apply a sim-control command and broadcast the new state.

    Raises:
        ValueError: when the command is unknown or required arguments are missing.
    """

    if command not in VALID_COMMANDS:
        raise ValueError(f"unknown sim-control command: {command}")
    if command == "seed" and seed is None:
        raise ValueError("seed command requires a seed value")

    state = await _load_state(workspace_id)

    if command == "start":
        state.status = "running"
    elif command == "stop":
        state.status = "stopped"
    elif command == "pause":
        state.status = "paused"
    elif command == "resume":
        state.status = "running"
    elif command == "reset":
        state.status = "idle"
        for runtime_key in _RUNTIME_PARAM_KEYS:
            state.params.pop(runtime_key, None)
    elif command == "seed":
        state.seed = int(seed)  # type: ignore[arg-type]
    elif command == "update_params":
        if params:
            state.params.update(params)

    state.version = await _next_version(workspace_id)
    state.last_actor = actor
    state.last_command = command
    state.updated_at = time.time()
    await _save_state(state)

    entry = SimControlHistoryEntry(
        workspace_id=workspace_id,
        version=state.version,
        command=command,
        actor=actor,
        seed=state.seed,
        params=dict(state.params),
        status=state.status,
        timestamp=state.updated_at,
    )
    await _append_history(entry)

    await publish(
        sim_control_channel(workspace_id),
        json.dumps(
            {
                "command": command,
                "actor": actor,
                "version": state.version,
                "status": state.status,
                "seed": state.seed,
                "params": state.params,
                "workspace_id": workspace_id,
                "updated_at": state.updated_at,
            }
        ),
    )
    return state


async def list_history(
    *, workspace_id: str, limit: int = _HISTORY_MAX
) -> list[SimControlHistoryEntry]:
    """Return chronologically ordered command history (oldest first)."""

    redis = await get_redis()
    key = _history_key(workspace_id)
    bound = max(1, min(limit, _HISTORY_MAX))
    raw_entries = await redis.lrange(key, -bound, -1)
    history: list[SimControlHistoryEntry] = []
    for raw in raw_entries:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        history.append(
            SimControlHistoryEntry(
                workspace_id=str(data.get("workspace_id", workspace_id)),
                version=int(data.get("version", 0)),
                command=str(data.get("command", "")),
                actor=str(data.get("actor", "")),
                seed=data.get("seed"),
                params=dict(data.get("params") or {}),
                status=str(data.get("status", "idle")),
                timestamp=float(data.get("timestamp", 0.0)),
            )
        )
    return history


async def clear_workspace(*, workspace_id: str) -> None:
    """Remove all persisted sim-control state for a workspace."""

    redis = await get_redis()
    pipe = redis.pipeline()
    pipe.delete(_state_key(workspace_id))
    pipe.delete(_version_key(workspace_id))
    pipe.delete(_history_key(workspace_id))
    await pipe.execute()
