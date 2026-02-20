"""Tests for the terminal WebSocket backend.

TDD: Define the expected behaviour of the session terminal service
before the implementation exists.
"""
from __future__ import annotations

import asyncio

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
# TerminalSession unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_terminal_session_create():
    """Creating a TerminalSession returns a handle with a PID."""
    from co_sim.services.terminal import TerminalSession

    ts = TerminalSession(session_id="s1", shell="/bin/sh")
    assert ts.session_id == "s1"
    assert ts.shell == "/bin/sh"
    assert not ts.is_alive


@pytest.mark.asyncio
async def test_terminal_session_start_stop():
    """start() spawns a subprocess and stop() terminates it."""
    from co_sim.services.terminal import TerminalSession

    ts = TerminalSession(session_id="s2", shell="/bin/sh")
    await ts.start()
    assert ts.is_alive
    assert ts.pid is not None
    assert ts.pid > 0

    await ts.stop()
    # Allow a brief moment for process cleanup
    await asyncio.sleep(0.1)
    assert not ts.is_alive


@pytest.mark.asyncio
async def test_terminal_session_write_and_read():
    """Writing a command to stdin produces output on stdout."""
    from co_sim.services.terminal import TerminalSession

    ts = TerminalSession(session_id="s3", shell="/bin/sh")
    await ts.start()

    try:
        await ts.write("echo hello_terminal\n")
        # Read output (with timeout)
        output = await asyncio.wait_for(ts.read_until("hello_terminal"), timeout=5.0)
        assert "hello_terminal" in output
    finally:
        await ts.stop()


@pytest.mark.asyncio
async def test_terminal_session_resize():
    """resize() updates the PTY dimensions without crashing."""
    from co_sim.services.terminal import TerminalSession

    ts = TerminalSession(session_id="s4", shell="/bin/sh")
    await ts.start()

    try:
        # Should not raise
        ts.resize(rows=40, cols=120)
    finally:
        await ts.stop()


@pytest.mark.asyncio
async def test_terminal_interrupt():
    """Sending interrupt (Ctrl+C / SIGINT) terminates a running command."""
    from co_sim.services.terminal import TerminalSession

    ts = TerminalSession(session_id="s5", shell="/bin/sh")
    await ts.start()

    try:
        # Start a long-running command
        await ts.write("sleep 60\n")
        await asyncio.sleep(0.3)

        # Send interrupt
        await ts.interrupt()
        await asyncio.sleep(0.5)

        # Shell should still be alive after interrupting a command
        assert ts.is_alive
    finally:
        await ts.stop()


# ---------------------------------------------------------------------------
# TerminalManager tests (multi-session)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_terminal_manager_create_and_get():
    """TerminalManager tracks sessions by session_id."""
    from co_sim.services.terminal import TerminalManager

    mgr = TerminalManager()
    ts = await mgr.get_or_create("sess-1")
    assert ts.is_alive

    # Getting the same ID returns the same session
    ts2 = await mgr.get_or_create("sess-1")
    assert ts.pid == ts2.pid

    await mgr.destroy("sess-1")
    assert mgr.get("sess-1") is None


@pytest.mark.asyncio
async def test_terminal_manager_destroy_all():
    """destroy_all() cleans up every terminal."""
    from co_sim.services.terminal import TerminalManager

    mgr = TerminalManager()
    await mgr.get_or_create("a")
    await mgr.get_or_create("b")

    assert len(mgr.sessions) == 2

    await mgr.destroy_all()
    assert len(mgr.sessions) == 0


# ---------------------------------------------------------------------------
# Redis state persistence for terminal sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_terminal_state_persisted():
    """Terminal session metadata persists to Redis."""
    from co_sim.services.terminal import persist_terminal_state, get_terminal_state

    await persist_terminal_state("sess-1", pid=12345, rows=24, cols=80)
    state = await get_terminal_state("sess-1")
    assert state is not None
    assert state["pid"] == "12345"
    assert state["rows"] == "24"


@pytest.mark.asyncio
async def test_terminal_state_removal():
    """Removing terminal state from Redis."""
    from co_sim.services.terminal import persist_terminal_state, get_terminal_state, remove_terminal_state

    await persist_terminal_state("sess-del", pid=999, rows=24, cols=80)
    assert await get_terminal_state("sess-del") is not None

    await remove_terminal_state("sess-del")
    assert await get_terminal_state("sess-del") is None
