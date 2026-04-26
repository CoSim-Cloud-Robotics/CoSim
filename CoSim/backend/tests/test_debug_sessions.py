"""Tests for the Python-only debug session service.

Phase 3 narrows debugger support to Python via ``debugpy`` and adds Redis
persistence so collaborators can discover live debug sessions without
holding an in-memory reference. The service also exposes a
``build_terminal_command`` helper used by the terminal backend to launch
``python -m debugpy`` interactively inside a PTY.
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
# Command building (Python-only)
# ---------------------------------------------------------------------------


def test_resolve_debug_command_python_basic():
    from co_sim.services.debug_sessions import resolve_debug_command

    cmd = resolve_debug_command(
        port=5678,
        file_path="/ws/main.py",
        args=["--epochs", "3"],
    )
    assert cmd[0].endswith("python") or cmd[0].endswith("python3")
    assert "-m" in cmd
    assert "debugpy" in cmd
    assert "--listen" in cmd
    assert "0.0.0.0:5678" in cmd
    assert "--wait-for-client" in cmd
    assert cmd[-3] == "/ws/main.py"
    assert cmd[-2:] == ["--epochs", "3"]


def test_resolve_debug_command_requires_file_path():
    from co_sim.services.debug_sessions import resolve_debug_command

    with pytest.raises(ValueError):
        resolve_debug_command(port=5678, file_path=None, args=[])


def test_build_terminal_command_quotes_args():
    """``build_terminal_command`` returns a single shell-friendly string for the PTY."""
    from co_sim.services.debug_sessions import build_terminal_command

    line = build_terminal_command(
        port=5678,
        file_path="/ws/path with spaces/main.py",
        args=["--name", "my run"],
    )
    assert "python" in line
    assert "-m debugpy" in line
    assert "--listen 0.0.0.0:5678" in line
    assert "--wait-for-client" in line
    # Both the path and the arg with spaces must be quoted/escaped.
    assert "'/ws/path with spaces/main.py'" in line or '"/ws/path with spaces/main.py"' in line
    assert "'my run'" in line or '"my run"' in line


# ---------------------------------------------------------------------------
# Redis persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_and_get_state_roundtrip():
    from co_sim.services.debug_sessions import (
        persist_debug_state,
        get_debug_state,
    )

    await persist_debug_state(
        debug_id="dbg-1",
        session_id="sess-1",
        workspace_id="ws-1",
        port=5678,
        command=["python", "-m", "debugpy", "--listen", "0.0.0.0:5678", "/ws/main.py"],
        working_dir="/ws",
    )
    state = await get_debug_state("dbg-1")
    assert state is not None
    assert state["debug_id"] == "dbg-1"
    assert state["session_id"] == "sess-1"
    assert state["workspace_id"] == "ws-1"
    assert int(state["port"]) == 5678
    assert "main.py" in state["command"]


@pytest.mark.asyncio
async def test_list_debug_sessions_for_workspace():
    from co_sim.services.debug_sessions import (
        persist_debug_state,
        list_debug_sessions,
    )

    await persist_debug_state(
        debug_id="dbg-a",
        session_id="sess-a",
        workspace_id="ws-1",
        port=5001,
        command=["python", "-m", "debugpy", "/x"],
        working_dir="/x",
    )
    await persist_debug_state(
        debug_id="dbg-b",
        session_id="sess-b",
        workspace_id="ws-1",
        port=5002,
        command=["python", "-m", "debugpy", "/y"],
        working_dir="/y",
    )
    await persist_debug_state(
        debug_id="dbg-c",
        session_id="sess-c",
        workspace_id="ws-2",
        port=5003,
        command=["python", "-m", "debugpy", "/z"],
        working_dir="/z",
    )

    ws1 = await list_debug_sessions(workspace_id="ws-1")
    ws2 = await list_debug_sessions(workspace_id="ws-2")
    assert {entry["debug_id"] for entry in ws1} == {"dbg-a", "dbg-b"}
    assert {entry["debug_id"] for entry in ws2} == {"dbg-c"}


@pytest.mark.asyncio
async def test_remove_debug_state():
    from co_sim.services.debug_sessions import (
        persist_debug_state,
        get_debug_state,
        remove_debug_state,
    )

    await persist_debug_state(
        debug_id="dbg-x",
        session_id="sess-x",
        workspace_id="ws-1",
        port=5009,
        command=["python", "-m", "debugpy", "/a"],
        working_dir="/a",
    )
    assert await get_debug_state("dbg-x") is not None
    removed = await remove_debug_state("dbg-x")
    assert removed is True
    assert await get_debug_state("dbg-x") is None


# ---------------------------------------------------------------------------
# Free-port helper
# ---------------------------------------------------------------------------


def test_find_free_port_returns_valid_port():
    from co_sim.services.debug_sessions import find_free_port

    port = find_free_port()
    assert 1 <= port <= 65535


# ---------------------------------------------------------------------------
# Terminal integration — attaching a debug session to an existing terminal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_to_terminal_sends_command():
    from co_sim.services import debug_sessions as dbg

    written: list[str] = []

    class _FakeTerminal:
        is_alive = True

        async def write(self, data: str) -> None:
            written.append(data)

    info = await dbg.attach_to_terminal(
        terminal=_FakeTerminal(),
        debug_id="dbg-1",
        session_id="sess-1",
        workspace_id="ws-1",
        file_path="/ws/main.py",
        port=5678,
        args=["--epochs", "1"],
        working_dir="/ws",
    )
    assert info["debug_id"] == "dbg-1"
    assert info["port"] == 5678
    assert any("debugpy" in line and "/ws/main.py" in line for line in written)
    # The command is finished with a newline so the shell actually executes it.
    assert any(line.endswith("\n") for line in written)

    # State should have been persisted for cross-process discovery.
    state = await dbg.get_debug_state("dbg-1")
    assert state is not None
    assert int(state["port"]) == 5678


@pytest.mark.asyncio
async def test_attach_to_terminal_requires_alive_terminal():
    from co_sim.services import debug_sessions as dbg

    class _DeadTerminal:
        is_alive = False

        async def write(self, data: str) -> None:  # pragma: no cover - guarded
            raise AssertionError("must not write to a dead terminal")

    with pytest.raises(RuntimeError):
        await dbg.attach_to_terminal(
            terminal=_DeadTerminal(),
            debug_id="dbg-2",
            session_id="sess-2",
            workspace_id="ws-2",
            file_path="/ws/main.py",
            port=5678,
            args=[],
            working_dir="/ws",
        )
