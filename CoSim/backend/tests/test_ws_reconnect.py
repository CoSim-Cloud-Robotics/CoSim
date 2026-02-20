"""Tests for WebSocket reconnection utilities.

TDD: Defines the expected behaviour of the reconnection manager
before it is implemented.
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
# Reconnection policy tests
# ---------------------------------------------------------------------------

def test_exponential_backoff_defaults():
    """Default backoff policy uses exponential delays with jitter."""
    from co_sim.services.ws_reconnect import ReconnectPolicy

    policy = ReconnectPolicy()
    assert policy.max_attempts == 10
    assert policy.base_delay == 1.0
    assert policy.max_delay == 30.0

    # First attempt should be ~1s, second ~2s, etc.
    d1 = policy.delay_for(1)
    d2 = policy.delay_for(2)
    d3 = policy.delay_for(3)
    assert 0 < d1 <= 2.0  # base * 2^0 = 1, with jitter
    assert d2 > d1 * 0.5  # roughly doubling
    assert d3 <= policy.max_delay


def test_exponential_backoff_caps_at_max():
    """Delay is capped at max_delay."""
    from co_sim.services.ws_reconnect import ReconnectPolicy

    policy = ReconnectPolicy(max_delay=5.0)
    for attempt in range(1, 20):
        assert policy.delay_for(attempt) <= 5.0 * 1.5  # max * jitter ceiling


def test_should_retry():
    """should_retry returns False after max_attempts."""
    from co_sim.services.ws_reconnect import ReconnectPolicy

    policy = ReconnectPolicy(max_attempts=3)
    assert policy.should_retry(1) is True
    assert policy.should_retry(3) is True
    assert policy.should_retry(4) is False


# ---------------------------------------------------------------------------
# ReconnectManager state machine tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reconnect_manager_lifecycle():
    """ReconnectManager tracks attempts and resets on success."""
    from co_sim.services.ws_reconnect import ReconnectManager

    mgr = ReconnectManager(name="test-ws")
    assert mgr.attempt == 0
    assert mgr.state == "disconnected"

    # Simulate connection attempt
    mgr.on_connecting()
    assert mgr.state == "connecting"

    # Connection succeeds
    mgr.on_connected()
    assert mgr.state == "connected"
    assert mgr.attempt == 0  # reset on success

    # Connection drops
    mgr.on_disconnected()
    assert mgr.state == "disconnected"
    assert mgr.attempt == 1


@pytest.mark.asyncio
async def test_reconnect_manager_gives_up():
    """After max attempts, state becomes 'failed'."""
    from co_sim.services.ws_reconnect import ReconnectManager, ReconnectPolicy

    policy = ReconnectPolicy(max_attempts=2)
    mgr = ReconnectManager(name="test", policy=policy)

    # Fail twice
    mgr.on_disconnected()
    assert mgr.state == "disconnected"
    assert mgr.attempt == 1

    mgr.on_disconnected()
    assert mgr.state == "disconnected"
    assert mgr.attempt == 2

    mgr.on_disconnected()
    assert mgr.state == "failed"
    assert mgr.attempt == 3


@pytest.mark.asyncio
async def test_reconnect_manager_manual_reset():
    """Manual reset clears attempt counter and sets state to disconnected."""
    from co_sim.services.ws_reconnect import ReconnectManager

    mgr = ReconnectManager(name="test")
    mgr.on_disconnected()
    mgr.on_disconnected()
    assert mgr.attempt == 2

    mgr.reset()
    assert mgr.attempt == 0
    assert mgr.state == "disconnected"


# ---------------------------------------------------------------------------
# Redis-backed reconnection state (for cross-process visibility)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reconnect_state_in_redis():
    """Connection state is persisted to Redis."""
    from co_sim.services.ws_reconnect import persist_connection_state, get_connection_state

    await persist_connection_state("sim-stream:sess-1", state="connected", attempt=0)
    info = await get_connection_state("sim-stream:sess-1")
    assert info is not None
    assert info["state"] == "connected"

    await persist_connection_state("sim-stream:sess-1", state="disconnected", attempt=3)
    info = await get_connection_state("sim-stream:sess-1")
    assert info["state"] == "disconnected"
    assert info["attempt"] == "3"
