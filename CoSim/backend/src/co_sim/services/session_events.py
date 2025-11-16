from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any, Awaitable, Callable

from redis.asyncio.client import PubSub

from co_sim.core.redis import get_redis
from co_sim.services.session_cache import SESSION_EVENTS_CHANNEL

_events: deque[dict[str, Any]] = deque(maxlen=50)
_listener_task: asyncio.Task | None = None
_pubsub: PubSub | None = None
_handlers: dict[str, Callable[[dict[str, Any]], Awaitable[None] | None]] = {}


async def start_listener() -> None:
    global _listener_task, _pubsub
    if _listener_task:
        return
    redis = await get_redis()
    _pubsub = redis.pubsub()
    await _pubsub.subscribe(SESSION_EVENTS_CHANNEL)

    async def _run() -> None:
        try:
            while True:
                message = await _pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    try:
                        data = json.loads(message.get("data"))
                    except json.JSONDecodeError:
                        data = {"raw": message.get("data")}
                    await emit_event(data)
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        finally:
            if _pubsub is not None:
                try:
                    await _pubsub.unsubscribe(SESSION_EVENTS_CHANNEL)
                    await _pubsub.close()
                finally:
                    pass

    _listener_task = asyncio.create_task(_run(), name="session-events-listener")


async def stop_listener() -> None:
    global _listener_task, _pubsub
    if _listener_task:
        _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass
    _listener_task = None
    _pubsub = None


async def _notify_handlers(event: dict[str, Any]) -> None:
    for handler in list(_handlers.values()):
        result = handler(event)
        if asyncio.iscoroutine(result):
            await result


def get_recent_events(limit: int = 20) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    return list(_events)[-limit:]


async def emit_event(event: dict[str, Any]) -> None:
    _events.append(event)
    await _notify_handlers(event)


def register_handler(name: str, handler: Callable[[dict[str, Any]], Awaitable[None] | None]) -> None:
    _handlers[name] = handler


def unregister_handler(name: str) -> None:
    _handlers.pop(name, None)
