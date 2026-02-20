"""WebSocket reconnection utilities.

Provides:
- ReconnectPolicy — exponential back-off with jitter
- ReconnectManager — state-machine for connection lifecycle
- Redis state persistence for connection metadata
"""
from __future__ import annotations

import random
from enum import Enum
from typing import Dict, Optional

from co_sim.core.redis import get_redis


# ---------------------------------------------------------------------------
# ReconnectPolicy — exponential back-off
# ---------------------------------------------------------------------------

class ReconnectPolicy:
    """Calculates exponential back-off delays with jitter."""

    def __init__(
        self,
        max_attempts: int = 10,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def delay_for(self, attempt: int) -> float:
        """Return the delay in seconds for a given attempt number (0-based)."""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay

    def should_retry(self, attempt: int) -> bool:
        """Return True if the given attempt number is within bounds."""
        return attempt <= self.max_attempts


# ---------------------------------------------------------------------------
# ReconnectManager — connection lifecycle state machine
# ---------------------------------------------------------------------------

class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class ReconnectManager:
    """Manages reconnection state transitions.

    Lifecycle:
        disconnected ──on_connecting()──▶ connecting
        connecting   ──on_connected()──▶  connected  (resets attempt)
        connected    ──on_disconnected()──▶ disconnected (increments attempt)
        disconnected ──on_disconnected()──▶ disconnected | failed (when exhausted)
    """

    def __init__(
        self,
        name: str = "default",
        policy: Optional[ReconnectPolicy] = None,
    ):
        self.name = name
        self.policy = policy or ReconnectPolicy()
        self._state = ConnectionState.DISCONNECTED
        self._attempt = 0

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def attempt(self) -> int:
        return self._attempt

    def on_connecting(self) -> None:
        """Transition to CONNECTING."""
        self._state = ConnectionState.CONNECTING

    def on_connected(self) -> None:
        """Transition to CONNECTED and reset attempt counter."""
        self._state = ConnectionState.CONNECTED
        self._attempt = 0

    def on_disconnected(self) -> None:
        """Transition to DISCONNECTED and increment attempt counter.

        If max attempts exceeded, transition to FAILED instead.
        """
        self._attempt += 1
        if not self.policy.should_retry(self._attempt):
            self._state = ConnectionState.FAILED
        else:
            self._state = ConnectionState.DISCONNECTED

    def reset(self) -> None:
        """Reset state machine to initial state."""
        self._state = ConnectionState.DISCONNECTED
        self._attempt = 0

    def delay_for_current_attempt(self) -> float:
        """Return the back-off delay for the current attempt number."""
        return self.policy.delay_for(self._attempt)


# ---------------------------------------------------------------------------
# Redis state persistence
# ---------------------------------------------------------------------------

_CONN_KEY_PREFIX = "cosim:ws_connection"


def _conn_key(connection_id: str) -> str:
    return f"{_CONN_KEY_PREFIX}:{connection_id}"


async def persist_connection_state(
    connection_id: str,
    state: str,
    attempt: int = 0,
    ttl: int = 3600,
) -> None:
    """Store WebSocket connection state in Redis."""
    redis = await get_redis()
    key = _conn_key(connection_id)
    await redis.hset(key, mapping={
        "state": state,
        "attempt": str(attempt),
    })
    await redis.expire(key, ttl)


async def get_connection_state(connection_id: str) -> Dict[str, str] | None:
    """Retrieve WebSocket connection state from Redis."""
    redis = await get_redis()
    data = await redis.hgetall(_conn_key(connection_id))
    return data if data else None
