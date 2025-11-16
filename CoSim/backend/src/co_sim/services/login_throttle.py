from __future__ import annotations

from co_sim.core.config import settings
from co_sim.core.redis import get_redis

_LOGIN_PREFIX = "auth:login"


class LoginThrottledError(Exception):
    """Raised when a login identifier exceeds the configured attempt limit."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Login throttled. Retry after {retry_after}s")


async def register_login_attempt(identifier: str) -> None:
    """Record an attempt and raise when exceeding configured limits."""

    redis = await get_redis()
    key = f"{_LOGIN_PREFIX}:{identifier}"
    attempts = await redis.incr(key)
    if attempts == 1:
        await redis.expire(key, settings.login_throttle_window_seconds)

    if attempts > settings.login_max_attempts:
        retry_after = await redis.ttl(key)
        raise LoginThrottledError(max(retry_after, 0))


async def reset_login_attempts(identifier: str) -> None:
    redis = await get_redis()
    await redis.delete(f"{_LOGIN_PREFIX}:{identifier}")
