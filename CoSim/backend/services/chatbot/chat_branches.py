"""Conversation branching for the CoSim chatbot.

A branch is a new conversation that copies the first ``fork_at_index``
messages from a parent and then diverges. Branch metadata is stored in a
Redis hash keyed ``chatbot:branches:<parent_id>`` so the UI can offer a
tree-style picker.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from redis_cache import HISTORY_TTL, fetch_history, get_client

_BRANCH_INDEX_PREFIX = "chatbot:branches"
_HISTORY_PREFIX = "chatbot:history"
_BRANCH_TTL = HISTORY_TTL


def _branch_index_key(parent_id: str) -> str:
    return f"{_BRANCH_INDEX_PREFIX}:{parent_id}"


def _history_key(conversation_id: str) -> str:
    return f"{_HISTORY_PREFIX}:{conversation_id}"


def create_branch(
    *,
    parent_id: str,
    fork_at_index: int,
    branch_name: str | None = None,
    branch_id: str | None = None,
) -> str:
    """Fork a conversation at ``fork_at_index`` (1-based, inclusive).

    Args:
        parent_id: The conversation to fork from (must already have history).
        fork_at_index: How many parent messages to copy (>=1, <= history len).
        branch_name: Optional human-friendly label.
        branch_id: Override the generated branch identifier (mainly for tests).

    Returns:
        The new branch's conversation id.
    """

    parent_history = fetch_history(parent_id, limit=200)
    if not parent_history:
        raise ValueError(f"unknown parent conversation: {parent_id}")
    if fork_at_index < 1 or fork_at_index > len(parent_history):
        raise ValueError(
            f"fork_at_index {fork_at_index} outside parent range 1..{len(parent_history)}"
        )

    new_id = branch_id or f"{parent_id}::branch::{uuid.uuid4().hex[:8]}"
    client = get_client()
    if client is None:
        raise RuntimeError("redis client not available")

    history_key = _history_key(new_id)
    pipe = client.pipeline()
    for message in parent_history[:fork_at_index]:
        pipe.rpush(history_key, json.dumps(message))
    pipe.expire(history_key, _BRANCH_TTL)

    metadata = {
        "branch_id": new_id,
        "parent_id": parent_id,
        "fork_at_index": fork_at_index,
        "name": branch_name or "branch",
        "created_at": time.time(),
    }
    pipe.hset(_branch_index_key(parent_id), new_id, json.dumps(metadata))
    pipe.expire(_branch_index_key(parent_id), _BRANCH_TTL)
    pipe.execute()
    return new_id


def list_branches(*, parent_id: str) -> list[dict[str, Any]]:
    """Return branch metadata for a parent (chronological order)."""

    client = get_client()
    if client is None:
        return []
    raw = client.hgetall(_branch_index_key(parent_id))
    if not raw:
        return []
    branches: list[dict[str, Any]] = []
    for value in raw.values():
        try:
            branches.append(json.loads(value))
        except json.JSONDecodeError:
            continue
    branches.sort(key=lambda entry: entry.get("created_at", 0.0))
    return branches
