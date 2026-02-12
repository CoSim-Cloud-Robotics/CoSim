from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from jose import jwt

from co_sim.core.config import settings
from co_sim.core.redis import get_redis

_TOKEN_BLACKLIST_PREFIX = "auth:token:blacklist"


def create_access_token(subject: UUID, scopes: str | None = None, expires_delta: timedelta | None = None) -> tuple[str, int]:
    expire_delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    expire = datetime.now(timezone.utc) + expire_delta
    token_id = uuid4().hex
    to_encode: dict[str, Any] = {"sub": str(subject), "exp": expire, "jti": token_id}
    if scopes:
        to_encode["scopes"] = scopes
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt, int(expire_delta.total_seconds())


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


async def blacklist_token(*, token: str | None = None, payload: dict[str, Any] | None = None) -> None:
    """Blacklist a token (by JWT string or decoded payload)."""

    data = payload or decode_token(token or "")
    token_id = data.get("jti")
    if not token_id:
        return
    ttl = _seconds_until_expiration(data)
    if ttl <= 0:
        return
    redis = await get_redis()
    await redis.setex(f"{_TOKEN_BLACKLIST_PREFIX}:{token_id}", ttl, "1")


async def is_token_blacklisted(token_id: str | None) -> bool:
    if not token_id:
        return False
    redis = await get_redis()
    return bool(await redis.exists(f"{_TOKEN_BLACKLIST_PREFIX}:{token_id}"))


def _seconds_until_expiration(payload: dict[str, Any]) -> int:
    exp = payload.get("exp")
    if isinstance(exp, datetime):
        expire_at = exp
    else:
        expire_at = datetime.fromtimestamp(int(exp), tz=timezone.utc)
    delta = expire_at - datetime.now(timezone.utc)
    return max(int(delta.total_seconds()), 0)
