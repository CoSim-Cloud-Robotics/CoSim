"""Streaming response helpers for the chatbot.

``stream_chunks`` consumes any iterable of text chunks (e.g. an Ollama or
OpenAI stream) and produces SSE-friendly event dicts that callers can
serialize via :func:`format_sse`. The accumulated assistant message is
appended to the conversation history when the generator terminates so a
client that drops mid-stream can still see what was answered on reconnect.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Iterable, Iterator

from redis_cache import append_history


def format_sse(event: dict[str, Any]) -> str:
    """Render an event dict as a Server-Sent-Events payload."""

    name = event.get("event", "message")
    data = event.get("data", {})
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def stream_chunks(
    *,
    conversation_id: str,
    prompt: str,
    generator: Iterable[str],
) -> Iterator[dict[str, Any]]:
    """Yield SSE events for each chunk and persist the final assistant reply."""

    accumulated: list[str] = []
    error: Exception | None = None
    iterator = iter(generator)
    while True:
        try:
            chunk = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001 - we surface every error to the client
            error = exc
            break
        accumulated.append(chunk)
        yield {
            "event": "chunk",
            "data": {
                "text": chunk,
                "index": len(accumulated) - 1,
                "wall_time": time.time(),
            },
        }

    final_text = "".join(accumulated)
    if final_text:
        append_history(
            conversation_id,
            {
                "role": "assistant",
                "content": final_text,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    if error is not None:
        yield {
            "event": "error",
            "data": {
                "error": str(error),
                "partial": final_text,
            },
        }
        return

    yield {
        "event": "done",
        "data": {
            "text": final_text,
            "chunks": len(accumulated),
            "wall_time": time.time(),
        },
    }


__all__ = ["format_sse", "stream_chunks"]
