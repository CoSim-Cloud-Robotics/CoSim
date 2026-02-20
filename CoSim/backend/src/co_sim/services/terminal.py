"""Terminal backend — PTY-based shell sessions for browser terminals.

Provides:
- TerminalSession — manages a single PTY subprocess
- TerminalManager — tracks multiple sessions
- Redis state persistence for cross-process visibility
"""
from __future__ import annotations

import asyncio
import os
import platform
import signal
from typing import Dict, Optional

from co_sim.core.redis import get_redis


# ---------------------------------------------------------------------------
# TerminalSession — wraps a PTY subprocess
# ---------------------------------------------------------------------------

class TerminalSession:
    """A single terminal session backed by a PTY subprocess."""

    def __init__(
        self,
        session_id: str,
        shell: str = "/bin/sh",
        rows: int = 24,
        cols: int = 80,
        env: Dict[str, str] | None = None,
    ):
        self.session_id = session_id
        self.shell = shell
        self.rows = rows
        self.cols = cols
        self.env = env or {}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._master_fd: Optional[int] = None
        self._slave_fd: Optional[int] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._pid: Optional[int] = None

    @property
    def is_alive(self) -> bool:
        if self._process is None:
            return False
        return self._process.returncode is None

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    async def start(self) -> None:
        """Spawn a shell subprocess with a PTY."""
        import pty
        import fcntl
        import struct
        import termios

        master_fd, slave_fd = pty.openpty()

        # Set initial terminal size
        winsize = struct.pack("HHHH", self.rows, self.cols, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        env = {**os.environ, **self.env, "TERM": "xterm-256color"}

        self._process = await asyncio.create_subprocess_exec(
            self.shell,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            preexec_fn=os.setsid,
        )

        os.close(slave_fd)
        self._master_fd = master_fd
        self._slave_fd = None
        self._pid = self._process.pid

        # Create an async reader for the master fd
        loop = asyncio.get_event_loop()
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        await loop.connect_read_pipe(lambda: protocol, os.fdopen(os.dup(master_fd), "rb", 0))

    async def stop(self) -> None:
        """Terminate the shell subprocess."""
        if self._process and self.is_alive:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        self._process = None
        self._pid = None

    async def write(self, data: str) -> None:
        """Write data to the terminal stdin."""
        if self._master_fd is None:
            raise RuntimeError("Terminal not started")
        os.write(self._master_fd, data.encode("utf-8"))

    async def read(self, size: int = 4096) -> str:
        """Read available output from the terminal."""
        if self._reader is None:
            raise RuntimeError("Terminal not started")
        try:
            data = await asyncio.wait_for(self._reader.read(size), timeout=1.0)
            return data.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            return ""

    async def read_until(self, marker: str, timeout: float = 5.0) -> str:
        """Read output until a marker string is found or timeout."""
        if self._reader is None:
            raise RuntimeError("Terminal not started")

        buffer = ""
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), timeout=min(remaining, 1.0))
                buffer += chunk.decode("utf-8", errors="replace")
                if marker in buffer:
                    return buffer
            except asyncio.TimeoutError:
                continue

        return buffer

    def resize(self, rows: int, cols: int) -> None:
        """Resize the PTY."""
        if self._master_fd is None:
            return
        import fcntl
        import struct
        import termios

        self.rows = rows
        self.cols = cols
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    async def interrupt(self) -> None:
        """Send SIGINT to the foreground process group."""
        if self._process and self.is_alive and self._pid:
            try:
                os.killpg(os.getpgid(self._pid), signal.SIGINT)
            except (ProcessLookupError, PermissionError):
                pass


# ---------------------------------------------------------------------------
# TerminalManager — tracks multiple sessions
# ---------------------------------------------------------------------------

class TerminalManager:
    """Manages multiple TerminalSession instances."""

    def __init__(self, default_shell: str = "/bin/sh"):
        self.sessions: Dict[str, TerminalSession] = {}
        self.default_shell = default_shell

    def get(self, session_id: str) -> Optional[TerminalSession]:
        return self.sessions.get(session_id)

    async def get_or_create(
        self,
        session_id: str,
        shell: str | None = None,
        rows: int = 24,
        cols: int = 80,
    ) -> TerminalSession:
        """Get an existing session or create a new one."""
        existing = self.sessions.get(session_id)
        if existing and existing.is_alive:
            return existing

        ts = TerminalSession(
            session_id=session_id,
            shell=shell or self.default_shell,
            rows=rows,
            cols=cols,
        )
        await ts.start()
        self.sessions[session_id] = ts
        return ts

    async def destroy(self, session_id: str) -> None:
        """Stop and remove a terminal session."""
        ts = self.sessions.pop(session_id, None)
        if ts:
            await ts.stop()

    async def destroy_all(self) -> None:
        """Stop all sessions."""
        for session_id in list(self.sessions.keys()):
            await self.destroy(session_id)


# ---------------------------------------------------------------------------
# Redis state persistence
# ---------------------------------------------------------------------------

_TERMINAL_KEY_PREFIX = "cosim:terminal"


def _terminal_key(session_id: str) -> str:
    return f"{_TERMINAL_KEY_PREFIX}:{session_id}"


async def persist_terminal_state(
    session_id: str,
    *,
    pid: int,
    rows: int = 24,
    cols: int = 80,
    ttl: int = 86400,
) -> None:
    """Store terminal session metadata in Redis."""
    redis = await get_redis()
    key = _terminal_key(session_id)
    await redis.hset(key, mapping={
        "pid": str(pid),
        "rows": str(rows),
        "cols": str(cols),
    })
    await redis.expire(key, ttl)


async def get_terminal_state(session_id: str) -> Dict[str, str] | None:
    """Retrieve terminal session metadata from Redis."""
    redis = await get_redis()
    data = await redis.hgetall(_terminal_key(session_id))
    return data if data else None


async def remove_terminal_state(session_id: str) -> None:
    """Remove terminal session metadata from Redis."""
    redis = await get_redis()
    await redis.delete(_terminal_key(session_id))
