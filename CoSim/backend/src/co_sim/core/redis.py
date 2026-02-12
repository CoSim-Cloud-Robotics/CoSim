from __future__ import annotations

import asyncio
import hashlib
import inspect
import secrets
from collections.abc import AsyncIterator
from typing import Callable

from redis.asyncio import Redis, from_url

from co_sim.core.config import settings

RedisFactory = Callable[[str], Redis]

_redis_client: Redis | None = None
_redis_lock = asyncio.Lock()


def _default_redis_factory(url: str) -> Redis:
    return from_url(url, encoding="utf-8", decode_responses=True)


_redis_factory: RedisFactory = _default_redis_factory

_CACHE_PREFIX = "cosim:cache"
_LOCK_PREFIX = "cosim:lock"
_CHANNEL_PREFIX = "cosim:channel"


def build_cache_identifier(*parts: str) -> str:
    """Create a deterministic hashed identifier for cache entries."""

    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part.encode("utf-8"))
        hasher.update(b"|")
    return hasher.hexdigest()


def _cache_key(namespace: str, identifier: str) -> str:
    return f"{_CACHE_PREFIX}:{namespace}:{identifier}"


def _lock_key(name: str) -> str:
    return f"{_LOCK_PREFIX}:{name}"


def _channel_name(name: str) -> str:
    return f"{_CHANNEL_PREFIX}:{name}"


async def init_redis(*, force: bool = False) -> Redis:
    """Initialize and cache the global Redis client.

    Args:
        force: When true, closes any existing client and re-creates the connection.

    Returns:
        A connected :class:`Redis` instance ready for use.
    """

    global _redis_client

    async with _redis_lock:
        if _redis_client is not None and not force:
            return _redis_client

        client = _redis_factory(settings.redis_url)
        await client.ping()

        if _redis_client is not None:
            await _close_client(_redis_client)

        _redis_client = client
        return _redis_client


async def get_redis() -> Redis:
    """Return the shared Redis client, initializing it if necessary."""

    if _redis_client is None:
        return await init_redis()
    return _redis_client


async def close_redis() -> None:
    """Close the shared Redis client if it exists."""

    global _redis_client

    async with _redis_lock:
        if _redis_client is None:
            return
        await _close_client(_redis_client)
        _redis_client = None


async def redis_dependency() -> AsyncIterator[Redis]:
    """FastAPI dependency that yields the shared Redis client."""

    client = await get_redis()
    yield client


async def cache_get(namespace: str, identifier: str) -> str | None:
    """Retrieve a cached value for the given namespace + identifier."""

    client = await get_redis()
    return await client.get(_cache_key(namespace, identifier))


async def cache_set(namespace: str, identifier: str, value: str, ttl_seconds: int) -> None:
    """Store a cached value with an expiration."""

    client = await get_redis()
    await client.setex(_cache_key(namespace, identifier), ttl_seconds, value)


async def cache_delete(namespace: str, identifier: str) -> None:
    """Remove a cached value."""

    client = await get_redis()
    await client.delete(_cache_key(namespace, identifier))


class RedisLock:
    """Simple async lock built on Redis SETNX semantics."""

    def __init__(
        self,
        name: str,
        *,
        ttl: int = 30,
        blocking: bool = True,
        blocking_timeout: float | None = 10.0,
    ) -> None:
        self._name = _lock_key(name)
        self._ttl = ttl
        self._blocking = blocking
        self._blocking_timeout = blocking_timeout
        self._token = secrets.token_hex(16)
        self._acquired = False

    async def acquire(self) -> bool:
        client = await get_redis()
        deadline: float | None = None
        loop = asyncio.get_running_loop()
        if self._blocking and self._blocking_timeout is not None:
            deadline = loop.time() + self._blocking_timeout

        while True:
            acquired = await client.set(self._name, self._token, nx=True, ex=self._ttl)
            if acquired:
                self._acquired = True
                return True
            if not self._blocking:
                return False
            if deadline is not None and loop.time() >= deadline:
                return False
            await asyncio.sleep(0.05)

    async def release(self) -> None:
        if not self._acquired:
            return
        client = await get_redis()
        current_value = await client.get(self._name)
        if current_value == self._token:
            await client.delete(self._name)
        self._acquired = False

    async def __aenter__(self) -> "RedisLock":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        await self.release()


async def publish(channel: str, message: str) -> int:
    """Publish a message to a namespaced Redis channel."""

    client = await get_redis()
    return await client.publish(_channel_name(channel), message)


async def subscribe(channel: str):
    """Subscribe to a namespaced channel and return the pubsub object."""

    client = await get_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(_channel_name(channel))
    return pubsub


def set_redis_factory(factory: RedisFactory) -> None:
    """Override the Redis factory (primarily for testing)."""

    global _redis_factory
    _redis_factory = factory


async def reset_redis_state() -> None:
    """Reset cached state (used by tests to ensure clean setup)."""

    global _redis_client, _redis_factory

    async with _redis_lock:
        if _redis_client is not None:
            await _close_client(_redis_client)
        _redis_client = None
        _redis_factory = _default_redis_factory


async def _close_client(client: Redis) -> None:
    """Close a Redis client, awaiting the result when necessary."""

    close_method = getattr(client, "aclose", None)
    if close_method is None:
        result = client.close()
    else:
        result = close_method()
    if inspect.isawaitable(result):
        await result
