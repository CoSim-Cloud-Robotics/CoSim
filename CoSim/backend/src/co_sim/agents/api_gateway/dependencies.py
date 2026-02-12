from __future__ import annotations

try:  # Python 3.8 compatibility
    from typing import Annotated
except ImportError:  # pragma: no cover
    from typing_extensions import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from co_sim.core.config import settings
from co_sim.core.redis import redis_dependency
from co_sim.typing import Annotated

RATE_LIMIT_PREFIX = "api-gateway:rate"


async def enforce_rate_limit(
    request: Request,
    redis: Annotated[Redis, Depends(redis_dependency)],
) -> None:
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return

    identifier = _extract_identifier(request)
    key = f"{RATE_LIMIT_PREFIX}:{identifier}"

    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, 60)

    if current > limit:
        retry_after = await redis.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Rate limit exceeded",
                "retry_after": max(retry_after, 0),
            },
        )


def _extract_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    client = request.client
    if client and client.host:
        return client.host
    return "unknown"
