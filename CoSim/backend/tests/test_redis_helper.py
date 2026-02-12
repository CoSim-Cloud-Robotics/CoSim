from __future__ import annotations

import asyncio
import os

import pytest
from fakeredis.aioredis import FakeRedis

os.environ.setdefault("COSIM_JWT_SECRET_KEY", "x" * 32)

from co_sim.core import redis as redis_helpers


@pytest.fixture(autouse=True)
async def reset_redis_state() -> None:
    await redis_helpers.reset_redis_state()
    yield
    await redis_helpers.reset_redis_state()


@pytest.mark.asyncio
async def test_init_and_get_redis_reuse_same_client():
    fake_client = FakeRedis(decode_responses=True)

    def factory(url: str) -> FakeRedis:
        assert url == redis_helpers.settings.redis_url
        return fake_client

    redis_helpers.set_redis_factory(factory)

    client = await redis_helpers.init_redis()
    assert client is fake_client

    cached_client = await redis_helpers.get_redis()
    assert cached_client is fake_client


@pytest.mark.asyncio
async def test_close_redis_disposes_client():
    fake_client = FakeRedis(decode_responses=True)
    redis_helpers.set_redis_factory(lambda _: fake_client)

    await redis_helpers.init_redis(force=True)
    await redis_helpers.close_redis()

    # After closing, init_redis should create a new client instance
    new_client_instance = FakeRedis(decode_responses=True)
    redis_helpers.set_redis_factory(lambda _: new_client_instance)

    client = await redis_helpers.get_redis()
    assert client is new_client_instance


@pytest.mark.asyncio
async def test_redis_dependency_yields_client():
    fake_client = FakeRedis(decode_responses=True)
    redis_helpers.set_redis_factory(lambda _: fake_client)

    await redis_helpers.init_redis(force=True)

    gen = redis_helpers.redis_dependency()
    client = await gen.__anext__()
    current = await redis_helpers.get_redis()
    assert client is current is fake_client
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


@pytest.mark.asyncio
async def test_cache_helpers_round_trip():
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)

    identifier = redis_helpers.build_cache_identifier("foo", "bar")
    await redis_helpers.cache_set("tests", identifier, "value", ttl_seconds=30)
    cached = await redis_helpers.cache_get("tests", identifier)
    assert cached == "value"

    await redis_helpers.cache_delete("tests", identifier)
    assert await redis_helpers.cache_get("tests", identifier) is None


@pytest.mark.asyncio
async def test_redis_lock_acquire_release():
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)

    lock_primary = redis_helpers.RedisLock("shared", ttl=5)
    assert await lock_primary.acquire()

    lock_secondary = redis_helpers.RedisLock("shared", ttl=5, blocking=False)
    assert not await lock_secondary.acquire()

    await lock_primary.release()

    assert await lock_secondary.acquire()
    await lock_secondary.release()


@pytest.mark.asyncio
async def test_publish_and_subscribe_roundtrip():
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)

    pubsub = await redis_helpers.subscribe("events")
    await redis_helpers.publish("events", "hello")

    message = None
    for _ in range(5):
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if message:
            break
        await asyncio.sleep(0.01)

    assert message is not None
    assert message["data"] == "hello"

    await pubsub.unsubscribe()
    close_method = getattr(pubsub, "aclose", None)
    if close_method:
        await close_method()
    else:
        await pubsub.close()
