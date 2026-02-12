"""Redis helpers for chatbot caching and coordination."""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Iterable

try:
    import redis
except ImportError:  # pragma: no cover - dependency missing in some environments
    redis = None  # type: ignore


_redis_client: redis.Redis | None = None  # type: ignore[valid-type]
_redis_unavailable = False

REDIS_URL = os.getenv("CHATBOT_REDIS_URL") or os.getenv("COSIM_REDIS_URL")
QUERY_CACHE_TTL = int(os.getenv("CHATBOT_QUERY_CACHE_TTL", "3600"))
HISTORY_TTL = int(os.getenv("CHATBOT_HISTORY_TTL", "86400"))
HISTORY_MAX = int(os.getenv("CHATBOT_HISTORY_MAX", "50"))
VECTOR_READY_TTL = int(os.getenv("CHATBOT_VECTOR_READY_TTL", "86400"))

_QUERY_PREFIX = "chatbot:query"
_HISTORY_PREFIX = "chatbot:history"
_VECTOR_READY_KEY = "chatbot:vector:ready"
_WARMUP_LOCK_KEY = "chatbot:vector:warmup"


def set_redis_client(client: redis.Redis | None) -> None:  # type: ignore[valid-type]
    global _redis_client, _redis_unavailable
    _redis_client = client
    _redis_unavailable = client is None


def get_client() -> redis.Redis | None:  # type: ignore[valid-type]
    global _redis_client, _redis_unavailable
    if _redis_client or _redis_unavailable:
        return _redis_client
    if redis is None or not REDIS_URL:
        _redis_unavailable = True
        return None
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as exc:  # pragma: no cover - network issues
        print(f"⚠️  Chatbot Redis unavailable: {exc}")
        _redis_unavailable = True
        return None


def _hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cache_query_results(query: str, n_results: int, results: list[dict[str, Any]]) -> None:
    client = get_client()
    if not client:
        return
    identifier = f"{query}:{n_results}"
    key = f"{_QUERY_PREFIX}:{_hash_identifier(identifier)}"
    try:
        client.setex(key, QUERY_CACHE_TTL, json.dumps(results))
    except Exception as exc:  # pragma: no cover - network issues
        print(f"⚠️  Failed to cache query: {exc}")


def get_cached_query_results(query: str, n_results: int) -> list[dict[str, Any]] | None:
    client = get_client()
    if not client:
        return None
    identifier = f"{query}:{n_results}"
    key = f"{_QUERY_PREFIX}:{_hash_identifier(identifier)}"
    payload = client.get(key)
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        client.delete(key)
        return None


def append_history(conversation_id: str, message: dict[str, Any], *, max_items: int | None = None) -> None:
    client = get_client()
    if not client:
        return
    if not conversation_id:
        return
    key = f"{_HISTORY_PREFIX}:{conversation_id}"
    limit = max_items or HISTORY_MAX
    try:
        client.rpush(key, json.dumps(message))
        client.ltrim(key, -limit, -1)
        client.expire(key, HISTORY_TTL)
    except Exception as exc:  # pragma: no cover
        print(f"⚠️  Failed to append conversation history: {exc}")


def fetch_history(conversation_id: str, limit: int) -> list[dict[str, Any]]:
    client = get_client()
    if not client or not conversation_id:
        return []
    limit = min(limit, HISTORY_MAX)
    key = f"{_HISTORY_PREFIX}:{conversation_id}"
    try:
        entries = client.lrange(key, -limit, -1)
        history: list[dict[str, Any]] = []
        for entry in entries:
            try:
                history.append(json.loads(entry))
            except json.JSONDecodeError:
                continue
        return history
    except Exception as exc:  # pragma: no cover
        print(f"⚠️  Failed to fetch conversation history: {exc}")
        return []


def acquire_warmup_lock(ttl: int = 300) -> bool:
    client = get_client()
    if not client:
        return False
    try:
        return bool(client.set(_WARMUP_LOCK_KEY, "1", nx=True, ex=ttl))
    except Exception:
        return False


def release_warmup_lock() -> None:
    client = get_client()
    if client:
        client.delete(_WARMUP_LOCK_KEY)


def mark_vector_ready() -> None:
    client = get_client()
    if client:
        client.set(_VECTOR_READY_KEY, "1", ex=VECTOR_READY_TTL)


def is_vector_ready() -> bool:
    client = get_client()
    if not client:
        return False
    return bool(client.exists(_VECTOR_READY_KEY))


def wait_for_vector_ready(timeout: int = 120) -> bool:
    client = get_client()
    if not client:
        return False
    end_time = time.time() + timeout
    while time.time() < end_time:
        if client.exists(_VECTOR_READY_KEY):
            return True
        time.sleep(1)
    return False


def reset_state() -> None:
    """Testing helper to clear globals"""
    global _redis_client, _redis_unavailable
    _redis_client = None
    _redis_unavailable = False
