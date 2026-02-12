from __future__ import annotations

import random
from typing import Optional

from co_sim.core.config import settings
from co_sim.core.redis import get_redis

_CODE_PREFIX = "auth:verification"


def _code_key(identifier: str) -> str:
    return f"{_CODE_PREFIX}:{identifier.lower()}"


async def generate_code(identifier: str, *, ttl_seconds: Optional[int] = None) -> str:
    code = f"{random.randint(0, 999999):06d}"
    redis = await get_redis()
    await redis.setex(_code_key(identifier), ttl_seconds or settings.verification_code_ttl_seconds, code)
    return code


async def validate_code(identifier: str, code: str, *, consume: bool = True) -> bool:
    redis = await get_redis()
    stored = await redis.get(_code_key(identifier))
    if stored and stored == code:
        if consume:
            await redis.delete(_code_key(identifier))
        return True
    return False
