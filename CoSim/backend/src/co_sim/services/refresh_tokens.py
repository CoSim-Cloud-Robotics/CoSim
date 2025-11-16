from __future__ import annotations

import secrets
from uuid import UUID

from co_sim.core.config import settings
from co_sim.core.redis import get_redis

_REFRESH_PREFIX = "auth:refresh"


def _refresh_key(token: str) -> str:
    return f"{_REFRESH_PREFIX}:{token}"


def _ttl_seconds() -> int:
    return settings.refresh_token_expire_minutes * 60


async def issue_refresh_token(user_id: UUID) -> str:
    token = secrets.token_urlsafe(48)
    redis = await get_redis()
    await redis.setex(_refresh_key(token), _ttl_seconds(), str(user_id))
    return token


async def rotate_refresh_token(old_token: str | None, user_id: UUID) -> str:
    if old_token:
        await revoke_refresh_token(old_token)
    return await issue_refresh_token(user_id)


async def revoke_refresh_token(token: str | None) -> None:
    if not token:
        return
    redis = await get_redis()
    await redis.delete(_refresh_key(token))


async def validate_refresh_token(token: str) -> UUID | None:
    redis = await get_redis()
    user_id = await redis.get(_refresh_key(token))
    if not user_id:
        return None
    return UUID(user_id)
