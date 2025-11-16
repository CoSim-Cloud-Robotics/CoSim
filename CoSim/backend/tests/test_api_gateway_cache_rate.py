from __future__ import annotations

import os

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import HTTPException
from starlette.requests import Request

from co_sim.agents.api_gateway.client import forward_request
from co_sim.agents.api_gateway.dependencies import enforce_rate_limit
from co_sim.core import redis as redis_helpers
from co_sim.core.config import settings

os.environ.setdefault("COSIM_JWT_SECRET_KEY", "x" * 32)


def _build_request(method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/test",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
async def _reset_redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


@pytest.mark.asyncio
async def test_forward_request_caches_get(monkeypatch):
    call_count = 0

    async def fake_request(self, method, url, **kwargs):  # noqa: ANN001, D401
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            status_code=200,
            content=b"{\"ok\": true}",
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    request = _build_request()

    resp1 = await forward_request(request, "auth", "/v1/sample")
    resp2 = await forward_request(request, "auth", "/v1/sample")

    assert call_count == 1
    assert resp1.json() == resp2.json() == {"ok": True}
    assert resp2.headers["X-Cache"] == "HIT"


@pytest.mark.asyncio
async def test_enforce_rate_limit_blocks_after_threshold(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    fake_request = _build_request()
    fake_redis = FakeRedis(decode_responses=True)

    await enforce_rate_limit(fake_request, fake_redis)
    await enforce_rate_limit(fake_request, fake_redis)

    with pytest.raises(HTTPException) as exc:
        await enforce_rate_limit(fake_request, fake_redis)

    assert exc.value.status_code == 429
    assert exc.value.detail["message"] == "Rate limit exceeded"
