from __future__ import annotations

import asyncio
import os
import shutil
import socket
import uuid
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.services import workspace_fs


@dataclass
class DebugSession:
    debug_id: str
    session_id: str
    workspace_id: str
    language: Literal["python", "cpp"]
    adapter: str | None
    port: int
    command: list[str]
    process: asyncio.subprocess.Process
    working_dir: str


_DEBUG_SESSIONS: dict[str, DebugSession] = {}


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("0.0.0.0", 0))
        return sock.getsockname()[1]


def _resolve_debug_command(
    language: Literal["python", "cpp"],
    *,
    port: int,
    file_path: str | None,
    binary_path: str | None,
    args: list[str],
    adapter: str | None,
) -> tuple[list[str], str | None]:
    if language == "python":
        if not file_path:
            raise ValueError("file_path required for python debugging")
        command = [
            shutil.which("python") or "python",
            "-m",
            "debugpy",
            "--listen",
            f"0.0.0.0:{port}",
            "--wait-for-client",
            file_path,
            *args,
        ]
        return command, None

    if not binary_path:
        raise ValueError("binary_path required for C++ debugging")

    adapter = adapter or ("gdb" if shutil.which("gdbserver") else "lldb")
    if adapter == "gdb":
        if not shutil.which("gdbserver"):
            raise ValueError("gdbserver not available")
        command = ["gdbserver", f"0.0.0.0:{port}", binary_path, *args]
    else:
        if not shutil.which("lldb-server"):
            raise ValueError("lldb-server not available")
        command = ["lldb-server", "gdbserver", f"0.0.0.0:{port}", binary_path, *args]
    return command, adapter


async def start_debug_session(
    session: AsyncSession,
    *,
    session_id: str,
    workspace_id: UUID | str,
    language: Literal["python", "cpp"],
    file_path: str | None,
    binary_path: str | None,
    args: list[str],
    adapter: str | None,
    port: int | None,
) -> DebugSession:
    await workspace_fs.sync_from_db(session, workspace_id)
    root = await workspace_fs.ensure_workspace_dir(workspace_id)

    resolved_file_path = (
        str(workspace_fs.resolve_workspace_path(workspace_id, file_path)) if file_path else None
    )
    resolved_binary_path = (
        str(workspace_fs.resolve_workspace_path(workspace_id, binary_path)) if binary_path else None
    )

    debug_port = port or _find_free_port()
    command, resolved_adapter = _resolve_debug_command(
        language,
        port=debug_port,
        file_path=resolved_file_path,
        binary_path=resolved_binary_path,
        args=args,
        adapter=adapter,
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
        language=language,
        adapter=resolved_adapter,
        port=debug_port,
        command=command,
        process=process,
        working_dir=str(root),
    )
    _DEBUG_SESSIONS[debug_id] = debug_session
    return debug_session


async def stop_debug_session(debug_id: str) -> bool:
    debug_session = _DEBUG_SESSIONS.pop(debug_id, None)
    if not debug_session:
        return False
    process = debug_session.process
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
    return True


def get_debug_session(debug_id: str) -> DebugSession | None:
    return _DEBUG_SESSIONS.get(debug_id)
