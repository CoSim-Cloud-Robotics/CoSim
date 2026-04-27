"""Phase 3 chatbot enhancements: streaming, branching, code-aware suggestions.

These tests cover the new modules added on top of ``redis_cache``:
- ``chat_branches`` — fork/list conversation branches
- ``chat_streaming`` — wrap a chunk generator with Redis persistence and SSE framing
- ``code_context`` — build code-aware system prompts and extract fenced code

Each test uses ``fakeredis`` so it runs offline.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

import fakeredis
import pytest

from redis_cache import (
    append_history,
    fetch_history,
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


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Conversation branching
# ---------------------------------------------------------------------------


def test_create_branch_copies_messages_up_to_index():
    from chat_branches import create_branch, list_branches

    parent = "conv-root"
    append_history(parent, _msg("user", "hi"), max_items=20)
    append_history(parent, _msg("assistant", "hello"), max_items=20)
    append_history(parent, _msg("user", "tell me about RL"), max_items=20)
    append_history(parent, _msg("assistant", "RL is..."), max_items=20)

    branch_id = create_branch(parent_id=parent, fork_at_index=2, branch_name="alt")
    assert branch_id != parent
    branch_history = fetch_history(branch_id, limit=20)
    assert len(branch_history) == 2
    assert branch_history[0]["content"] == "hi"
    assert branch_history[1]["content"] == "hello"

    branches = list_branches(parent_id=parent)
    assert any(b["branch_id"] == branch_id for b in branches)
    branch = next(b for b in branches if b["branch_id"] == branch_id)
    assert branch["fork_at_index"] == 2
    assert branch["name"] == "alt"
    assert branch["parent_id"] == parent


def test_create_branch_diverges_from_parent():
    from chat_branches import create_branch

    parent = "conv-root"
    append_history(parent, _msg("user", "q1"), max_items=20)
    append_history(parent, _msg("assistant", "a1"), max_items=20)

    branch_id = create_branch(parent_id=parent, fork_at_index=2)
    append_history(branch_id, _msg("user", "alt q2"), max_items=20)

    parent_history = fetch_history(parent, limit=20)
    branch_history = fetch_history(branch_id, limit=20)
    assert len(parent_history) == 2
    assert len(branch_history) == 3
    assert branch_history[-1]["content"] == "alt q2"


def test_create_branch_rejects_unknown_parent():
    from chat_branches import create_branch

    with pytest.raises(ValueError):
        create_branch(parent_id="nope", fork_at_index=1)


def test_create_branch_rejects_invalid_fork_index():
    from chat_branches import create_branch

    parent = "conv-root"
    append_history(parent, _msg("user", "hi"), max_items=20)
    with pytest.raises(ValueError):
        create_branch(parent_id=parent, fork_at_index=0)
    with pytest.raises(ValueError):
        create_branch(parent_id=parent, fork_at_index=10)


def test_list_branches_returns_empty_when_no_forks():
    from chat_branches import list_branches

    assert list_branches(parent_id="never-existed") == []


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def _gen(chunks: Iterable[str]):
    for chunk in chunks:
        yield chunk


def test_stream_chunks_yields_sse_events_and_persists():
    from chat_streaming import stream_chunks

    parent = "conv-stream"
    append_history(parent, _msg("user", "what is RL?"), max_items=20)

    events = list(
        stream_chunks(
            conversation_id=parent,
            prompt="what is RL?",
            generator=_gen(["Reinforcement ", "learning ", "is..."]),
        )
    )
    # Expect (chunks N) + final "done" event
    assert len(events) == 4
    assert events[0]["event"] == "chunk"
    assert events[0]["data"]["text"] == "Reinforcement "
    assert events[-1]["event"] == "done"
    final_text = events[-1]["data"]["text"]
    assert final_text == "Reinforcement learning is..."

    # Persisted assistant message visible in history.
    history = fetch_history(parent, limit=20)
    assert history[-1]["role"] == "assistant"
    assert history[-1]["content"] == final_text


def test_stream_chunks_handles_generator_error():
    from chat_streaming import stream_chunks

    def faulty():
        yield "partial "
        raise RuntimeError("boom")

    events = list(
        stream_chunks(
            conversation_id="conv-err",
            prompt="hi",
            generator=faulty(),
        )
    )
    types = [e["event"] for e in events]
    assert types[0] == "chunk"
    assert types[-1] == "error"
    assert "boom" in events[-1]["data"]["error"]


def test_stream_chunks_format_sse_serialization():
    from chat_streaming import format_sse

    payload = format_sse({"event": "chunk", "data": {"text": "hi"}})
    assert payload.startswith("event: chunk\n")
    assert "data: " in payload
    assert payload.endswith("\n\n")


# ---------------------------------------------------------------------------
# Context-aware code suggestions
# ---------------------------------------------------------------------------


def test_format_code_context_includes_file_and_snippet():
    from code_context import format_code_context

    snippet = "def add(a, b):\n    return a + b\n"
    prompt = format_code_context(
        file_path="src/math.py",
        language="python",
        snippet=snippet,
        selection={"start_line": 1, "end_line": 2},
        recent_diagnostics=["unused import os"],
    )
    assert "src/math.py" in prompt
    assert "```python" in prompt
    assert "def add(a, b)" in prompt
    assert "unused import os" in prompt
    assert "selection" in prompt.lower() or "lines 1-2" in prompt.lower()


def test_format_code_context_truncates_large_snippets():
    from code_context import format_code_context, MAX_SNIPPET_CHARS

    big = "x" * (MAX_SNIPPET_CHARS * 3)
    prompt = format_code_context(
        file_path="a.py",
        language="python",
        snippet=big,
        selection=None,
        recent_diagnostics=[],
    )
    # Truncated snippet should fit inside the prompt with an ellipsis.
    assert "..." in prompt
    assert len(prompt) < len(big) + 2_000


def test_extract_code_suggestion_parses_fenced_block():
    from code_context import extract_code_suggestion

    response = (
        "Sure! Here's an updated version:\n"
        "```python\n"
        "def add(a, b):\n"
        "    return a + b + 1\n"
        "```\n"
        "Let me know if that helps."
    )
    suggestion = extract_code_suggestion(response)
    assert suggestion is not None
    assert suggestion["language"] == "python"
    assert "return a + b + 1" in suggestion["code"]


def test_extract_code_suggestion_returns_none_when_absent():
    from code_context import extract_code_suggestion

    assert extract_code_suggestion("no code here, just chatting") is None


def test_format_code_context_handles_missing_optional_fields():
    from code_context import format_code_context

    prompt = format_code_context(
        file_path="a.py",
        language="python",
        snippet="print('hi')\n",
        selection=None,
        recent_diagnostics=None,
    )
    assert "a.py" in prompt
    assert "```python" in prompt
