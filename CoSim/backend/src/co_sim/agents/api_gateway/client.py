from __future__ import annotations

import json as jsonlib
from collections.abc import Mapping
from typing import Any

import httpx
from fastapi import HTTPException, Request, status

from co_sim.core.config import settings
from co_sim.core.redis import build_cache_identifier, cache_get, cache_set

SERVICE_MAP = {
    "auth": settings.service_endpoints.auth_base_url.rstrip("/"),
    "project": settings.service_endpoints.project_base_url.rstrip("/"),
    "session": settings.service_endpoints.session_base_url.rstrip("/"),
    "collab": settings.service_endpoints.collab_base_url.rstrip("/"),
}

CACHE_NAMESPACE = "api-gateway"


async def forward_request(
    request: Request,
    service_key: str,
    path: str,
    method: str = "GET",
    json: Any | None = None,
    params: Mapping[str, Any] | None = None,
    content: Any | None = None,
) -> httpx.Response:
    method_upper = method.upper()
    base_url = SERVICE_MAP.get(service_key)
    if not base_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Service not configured")

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in {"authorization", "x-request-id", "content-type"}
    }

    cache_identifier: str | None = None
    use_cache = method_upper == "GET" and settings.api_cache_ttl_seconds > 0
    if use_cache:
        cache_identifier = build_cache_identifier(
            service_key,
            path,
            jsonlib.dumps(params or {}, sort_keys=True),
            headers.get("authorization", ""),
        )
        cached_payload = await cache_get(CACHE_NAMESPACE, cache_identifier)
        if cached_payload:
            cached_response = _build_cached_response(cached_payload)
            return cached_response

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        response = await client.request(
            method=method_upper,
            url=f"{base_url}{path}",
            json=json,
            params=params,
            headers=headers,
            content=content,
        )

    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = {"error": response.text}
        raise HTTPException(status_code=response.status_code, detail=detail)

    if use_cache and cache_identifier:
        await _store_in_cache(cache_identifier, response)
    return response


def _build_cached_response(payload: str) -> httpx.Response:
    data = jsonlib.loads(payload)
    response = httpx.Response(
        status_code=data["status"],
        content=data["body"].encode("utf-8"),
        headers=data.get("headers") or {},
    )
    response.headers["X-Cache"] = "HIT"
    return response


async def _store_in_cache(identifier: str, response: httpx.Response) -> None:
    if response.status_code != 200:
        return
    payload = jsonlib.dumps(
        {
            "status": response.status_code,
            "body": response.text,
            "headers": {
                "content-type": response.headers.get("content-type", "application/json"),
            },
        }
    )
    await cache_set(CACHE_NAMESPACE, identifier, payload, settings.api_cache_ttl_seconds)
