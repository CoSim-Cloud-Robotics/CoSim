from __future__ import annotations

import os
from uuid import uuid4

import asyncio
import time

import pytest

os.environ.setdefault("COSIM_JWT_SECRET_KEY", "x" * 32)

from co_sim.core import redis as redis_helpers
from co_sim.core.config import settings
from co_sim.services import login_throttle
from co_sim.services import refresh_tokens, verification_codes
from co_sim.services import token as token_service


class InMemoryRedis:
    def __init__(self) -> None:
        self.store: dict[str, str | int] = {}
        self.expirations: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def incr(self, key: str) -> int:
        async with self._lock:
            value = int(self.store.get(key, 0)) + 1
            self.store[key] = value
            return value

    async def expire(self, key: str, ttl: int) -> bool:
        async with self._lock:
            self.expirations[key] = time.time() + ttl
            return True

    async def ttl(self, key: str) -> int:
        exp = self.expirations.get(key)
        if exp is None:
            return -2
        remaining = int(exp - time.time())
        return remaining if remaining > 0 else -2

    async def delete(self, key: str) -> int:
        async with self._lock:
            existed = 1 if key in self.store else 0
            self.store.pop(key, None)
            self.expirations.pop(key, None)
            return existed

    async def setex(self, key: str, ttl: int, value: str) -> bool:
        async with self._lock:
            self.store[key] = value
            self.expirations[key] = time.time() + ttl
            return True

    async def get(self, key: str) -> str | None:
        async with self._lock:
            exp = self.expirations.get(key)
            if exp is not None and exp < time.time():
                self.store.pop(key, None)
                self.expirations.pop(key, None)
                return None
            value = self.store.get(key)
            return str(value) if value is not None else None

    async def exists(self, key: str) -> int:
        return 1 if await self.get(key) is not None else 0


@pytest.fixture(autouse=True)
async def _mock_redis():
    await redis_helpers.reset_redis_state()

    def factory(_: str) -> InMemoryRedis:
        return InMemoryRedis()

    redis_helpers.set_redis_factory(factory)
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


@pytest.mark.asyncio
async def test_login_throttle_blocks_after_limit():
    identifier = "user@example.com:1.1.1.1"
    for _ in range(settings.login_max_attempts):
        await login_throttle.register_login_attempt(identifier)

    with pytest.raises(login_throttle.LoginThrottledError) as exc:
        await login_throttle.register_login_attempt(identifier)

    assert exc.value.retry_after >= 0

    await login_throttle.reset_login_attempts(identifier)
    await login_throttle.register_login_attempt(identifier)


@pytest.mark.asyncio
async def test_token_blacklist_marks_revoked_token():
    token, _ = token_service.create_access_token(subject=uuid4())
    payload = token_service.decode_token(token)
    jti = payload.get("jti")
    assert jti
    assert await token_service.is_token_blacklisted(jti) is False

    await token_service.blacklist_token(payload=payload)

    assert await token_service.is_token_blacklisted(jti) is True


@pytest.mark.asyncio
async def test_refresh_token_rotation():
    user_id = uuid4()
    token = await refresh_tokens.issue_refresh_token(user_id)
    assert await refresh_tokens.validate_refresh_token(token) == user_id

    rotated = await refresh_tokens.rotate_refresh_token(token, user_id)
    assert rotated != token
    assert await refresh_tokens.validate_refresh_token(token) is None
    assert await refresh_tokens.validate_refresh_token(rotated) == user_id


@pytest.mark.asyncio
async def test_verification_code_flow():
    identifier = "tester@example.com"
    code = await verification_codes.generate_code(identifier, ttl_seconds=30)
    assert await verification_codes.validate_code(identifier, code) is True
    assert await verification_codes.validate_code(identifier, code) is False
