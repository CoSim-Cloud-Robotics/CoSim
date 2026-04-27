"""Python-only debugger sessions backed by ``debugpy``.

Phase 3 narrows debugger support to Python (the platform's only supported
runtime). Sessions can be launched two ways:

1. **Headless** — ``start_debug_session`` spawns ``python -m debugpy`` as a
   detached subprocess and stores its handle in memory. Useful when the
   editor wants a long-lived debug adapter without an interactive terminal.

2. **Terminal-attached** — ``attach_to_terminal`` writes the equivalent
   ``python -m debugpy`` command into an existing PTY-backed terminal so the
   user sees stdout/stderr in their browser shell while debugpy listens on
   the assigned port.

Both paths persist a small descriptor to Redis (``cosim:debug:<debug_id>``)
so other backend processes can discover live debug sessions for a workspace.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import socket
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.core.redis import get_redis
from co_sim.services import workspace_fs

_DEBUG_KEY_PREFIX = "cosim:debug"
_WORKSPACE_INDEX_PREFIX = "cosim:debug:workspace"
_DEFAULT_TTL_SECONDS = 60 * 60 * 24


def _debug_key(debug_id: str) -> str:
    return f"{_DEBUG_KEY_PREFIX}:{debug_id}"


def _workspace_index_key(workspace_id: str) -> str:
    return f"{_WORKSPACE_INDEX_PREFIX}:{workspace_id}"


@dataclass
class DebugSession:
    debug_id: str
    session_id: str
    workspace_id: str
    port: int
    command: list[str]
    process: Optional[asyncio.subprocess.Process]
    working_dir: str
    language: str = "python"


_DEBUG_SESSIONS: dict[str, DebugSession] = {}


class _TerminalLike(Protocol):
    is_alive: bool

    async def write(self, data: str) -> None: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def find_free_port() -> int:
    """Return an unused TCP port suitable for binding debugpy."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("0.0.0.0", 0))
        return sock.getsockname()[1]


def resolve_debug_command(
    *,
    port: int,
    file_path: Optional[str],
    args: list[str],
) -> list[str]:
    """Build the ``python -m debugpy`` argv list for a Python debug session."""

    if not file_path:
        raise ValueError("file_path required for python debugging")
    python_executable = shutil.which("python") or shutil.which("python3") or "python"
    return [
        python_executable,
        "-m",
        "debugpy",
        "--listen",
        f"0.0.0.0:{port}",
        "--wait-for-client",
        file_path,
        *args,
    ]


def build_terminal_command(
    *,
    port: int,
    file_path: str,
    args: list[str],
) -> str:
    """Render the debugpy command as a single shell-safe string for a PTY."""

    argv = resolve_debug_command(port=port, file_path=file_path, args=args)
    return " ".join(shlex.quote(part) for part in argv)


# ---------------------------------------------------------------------------
# Redis persistence
# ---------------------------------------------------------------------------


async def persist_debug_state(
    *,
    debug_id: str,
    session_id: str,
    workspace_id: str,
    port: int,
    command: list[str],
    working_dir: str,
    ttl: int = _DEFAULT_TTL_SECONDS,
) -> None:
    """Persist debug session metadata for cross-process discovery."""

    redis = await get_redis()
    payload = {
        "debug_id": debug_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "port": str(port),
        "command": json.dumps(command),
        "working_dir": working_dir,
        "language": "python",
    }
    pipe = redis.pipeline()
    pipe.hset(_debug_key(debug_id), mapping=payload)
    pipe.expire(_debug_key(debug_id), ttl)
    pipe.sadd(_workspace_index_key(workspace_id), debug_id)
    pipe.expire(_workspace_index_key(workspace_id), ttl)
    await pipe.execute()


async def get_debug_state(debug_id: str) -> Optional[dict[str, str]]:
    """Return the persisted descriptor for a debug session if present."""

    redis = await get_redis()
    data = await redis.hgetall(_debug_key(debug_id))
    return data if data else None


async def list_debug_sessions(*, workspace_id: str) -> list[dict[str, str]]:
    """List every persisted debug session for a workspace."""

    redis = await get_redis()
    debug_ids = await redis.smembers(_workspace_index_key(workspace_id))
    if not debug_ids:
        return []
    sessions: list[dict[str, str]] = []
    for debug_id in sorted(debug_ids):
        data = await redis.hgetall(_debug_key(debug_id))
        if data:
            sessions.append(data)
    return sessions


async def remove_debug_state(debug_id: str) -> bool:
    """Remove a debug session descriptor from Redis."""

    redis = await get_redis()
    state = await redis.hgetall(_debug_key(debug_id))
    if not state:
        return False
    workspace_id = state.get("workspace_id")
    pipe = redis.pipeline()
    pipe.delete(_debug_key(debug_id))
    if workspace_id:
        pipe.srem(_workspace_index_key(workspace_id), debug_id)
    await pipe.execute()
    return True


# ---------------------------------------------------------------------------
# Headless debug session (subprocess-managed)
# ---------------------------------------------------------------------------


async def start_debug_session(
    session: AsyncSession,
    *,
    session_id: str,
    workspace_id: UUID | str,
    file_path: Optional[str],
    args: list[str],
    port: Optional[int] = None,
    # Legacy keyword arguments retained for API compatibility — Python is the
    # only supported language so they're ignored.
    language: Optional[str] = None,
    binary_path: Optional[str] = None,
    adapter: Optional[str] = None,
) -> DebugSession:
    if language is not None and language != "python":
        raise ValueError("only python debugging is supported")
    _ = binary_path, adapter  # explicitly ignored

    await workspace_fs.sync_from_db(session, workspace_id)
    root = await workspace_fs.ensure_workspace_dir(workspace_id)

    resolved_file_path = (
        str(workspace_fs.resolve_workspace_path(workspace_id, file_path))
        if file_path
        else None
    )

    debug_port = port or find_free_port()
    command = resolve_debug_command(
        port=debug_port, file_path=resolved_file_path, args=args
    )

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(root),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    debug_id = str(uuid.uuid4())
    debug_session = DebugSession(
        debug_id=debug_id,
        session_id=session_id,
        workspace_id=str(workspace_id),
        port=debug_port,
        command=command,
        process=process,
        working_dir=str(root),
    )
    _DEBUG_SESSIONS[debug_id] = debug_session
    await persist_debug_state(
        debug_id=debug_id,
        session_id=session_id,
        workspace_id=str(workspace_id),
        port=debug_port,
        command=command,
        working_dir=str(root),
    )
    return debug_session


async def stop_debug_session(debug_id: str) -> bool:
    """Stop a headless debug session (and clear its Redis descriptor)."""

    debug_session = _DEBUG_SESSIONS.pop(debug_id, None)
    if not debug_session:
        # Still try to clean up Redis state if any.
        return await remove_debug_state(debug_id)
    process = debug_session.process
    if process is not None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
    await remove_debug_state(debug_id)
    return True


def get_debug_session(debug_id: str) -> Optional[DebugSession]:
    return _DEBUG_SESSIONS.get(debug_id)


# ---------------------------------------------------------------------------
# Terminal-attached debug session
# ---------------------------------------------------------------------------


async def attach_to_terminal(
    *,
    terminal: _TerminalLike,
    debug_id: str,
    session_id: str,
    workspace_id: str,
    file_path: str,
    port: int,
    args: list[str],
    working_dir: str,
) -> Mapping[str, Any]:
    """Launch a Python debug session inside an existing terminal.

    The caller owns the terminal; this helper writes the ``python -m debugpy``
    invocation into its stdin and persists the descriptor to Redis so the
    rest of the platform can discover it.
    """

    if not getattr(terminal, "is_alive", False):
        raise RuntimeError("terminal is not alive — cannot attach debugger")

    command_line = build_terminal_command(port=port, file_path=file_path, args=args)
    await terminal.write(command_line + "\n")

    command_argv = resolve_debug_command(port=port, file_path=file_path, args=args)
    await persist_debug_state(
        debug_id=debug_id,
        session_id=session_id,
        workspace_id=workspace_id,
        port=port,
        command=command_argv,
        working_dir=working_dir,
    )

    return {
        "debug_id": debug_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "port": port,
        "command": command_argv,
        "command_line": command_line,
        "working_dir": working_dir,
        "language": "python",
    }
