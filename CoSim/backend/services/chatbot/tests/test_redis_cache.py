from __future__ import annotations

import pytest
from datetime import datetime

import fakeredis

from redis_cache import (
    append_history,
    cache_query_results,
    fetch_history,
    get_cached_query_results,
    acquire_warmup_lock,
    mark_vector_ready,
    release_warmup_lock,
    reset_state,
    set_redis_client,
)


@pytest.fixture(autouse=True)
def _redis_client():
    reset_state()
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_redis_client(fake)
    yield fake
    reset_state()


def test_query_cache_roundtrip():
    results = [{"content": "answer", "metadata": {"section": "FAQ"}, "distance": 0.1}]
    cache_query_results("hello", 3, results)
    cached = get_cached_query_results("hello", 3)
    assert cached == results
    assert get_cached_query_results("hello", 2) is None


def test_history_persistence(_redis_client):
    conversation_id = "conv-1"
    append_history(conversation_id, {"role": "user", "content": "hi", "timestamp": datetime.utcnow().isoformat()}, max_items=3)
    append_history(conversation_id, {"role": "assistant", "content": "hello", "timestamp": datetime.utcnow().isoformat()}, max_items=3)
    history = fetch_history(conversation_id, limit=5)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_warmup_lock_only_allows_single_holder():
    assert acquire_warmup_lock(ttl=1)
    assert not acquire_warmup_lock(ttl=1)
    release_warmup_lock()
    assert acquire_warmup_lock(ttl=1)
    mark_vector_ready()
