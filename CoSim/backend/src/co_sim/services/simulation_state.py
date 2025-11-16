"""Redis-backed persistence utilities for simulator state and frame fan-out."""
from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel, Field
from redis.asyncio.client import PubSub

from co_sim.core.redis import get_redis, publish, subscribe

_SIMULATION_INDEX_KEY = "simulations:index"
_SIMULATION_CONFIG_KEY = "simulations:config"
_SIMULATION_STATE_KEY = "simulations:state"
_FRAME_CHANNEL_PREFIX = "simulations:frames"


def _config_key(session_id: str) -> str:
    return f"{_SIMULATION_CONFIG_KEY}:{session_id}"


def _state_key(session_id: str) -> str:
    return f"{_SIMULATION_STATE_KEY}:{session_id}"


def _frame_channel(session_id: str) -> str:
    return f"{_FRAME_CHANNEL_PREFIX}:{session_id}"


class SimulationConfig(BaseModel):
    """Configuration persisted for each simulation instance."""

    session_id: str
    engine: str
    model_path: str | None = None
    width: int = 640
    height: int = 480
    fps: int = 60
    headless: bool = True


class SimulationRuntimeState(BaseModel):
    """Runtime telemetry mirrored into Redis."""

    session_id: str
    status: str = "idle"
    frame: int = 0
    time: float = 0.0
    is_streaming: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


async def persist_config(config: SimulationConfig) -> None:
    """Store simulation configuration and index membership."""

    redis = await get_redis()
    pipe = redis.pipeline()
    pipe.sadd(_SIMULATION_INDEX_KEY, config.session_id)
    pipe.set(_config_key(config.session_id), config.model_dump_json())
    await pipe.execute()


async def remove_simulation(session_id: str) -> None:
    """Remove configuration and cached state for a session."""

    redis = await get_redis()
    pipe = redis.pipeline()
    pipe.srem(_SIMULATION_INDEX_KEY, session_id)
    pipe.delete(_config_key(session_id))
    pipe.delete(_state_key(session_id))
    await pipe.execute()


async def get_config(session_id: str) -> SimulationConfig | None:
    """Fetch a persisted config if it exists."""

    redis = await get_redis()
    payload = await redis.get(_config_key(session_id))
    if not payload:
        return None
    return SimulationConfig.model_validate_json(payload)


async def list_configs() -> list[SimulationConfig]:
    """Return configs for every registered simulation."""

    redis = await get_redis()
    session_ids = await redis.smembers(_SIMULATION_INDEX_KEY)
    if not session_ids:
        return []

    pipe = redis.pipeline()
    ordered_ids = sorted(session_ids)
    for session_id in ordered_ids:
        pipe.get(_config_key(session_id))
    payloads = await pipe.execute()

    configs: list[SimulationConfig] = []
    for payload in payloads:
        if payload:
            configs.append(SimulationConfig.model_validate_json(payload))
    return configs


async def list_session_ids() -> list[str]:
    """Return sorted session identifiers tracked in Redis."""

    redis = await get_redis()
    session_ids = await redis.smembers(_SIMULATION_INDEX_KEY)
    if not session_ids:
        return []
    return sorted(session_ids)


async def update_state(
    session_id: str,
    state: dict[str, Any],
    *,
    status: str,
    streaming: bool,
) -> None:
    """Persist runtime telemetry for later inspection/resume."""

    runtime_state = SimulationRuntimeState(
        session_id=session_id,
        status=status,
        is_streaming=streaming,
        frame=int(state.get("frame", 0) or 0),
        time=float(state.get("time", 0.0) or 0.0),
        data=state,
    )
    redis = await get_redis()
    await redis.set(_state_key(session_id), runtime_state.model_dump_json())


async def get_state(session_id: str) -> SimulationRuntimeState | None:
    """Return the cached runtime state if available."""

    redis = await get_redis()
    payload = await redis.get(_state_key(session_id))
    if not payload:
        return None
    return SimulationRuntimeState.model_validate_json(payload)


async def publish_frame(session_id: str, frame_bytes: bytes) -> None:
    """Publish a base64 encoded frame to the Redis channel."""

    encoded = base64.b64encode(frame_bytes).decode("ascii")
    await publish(_frame_channel(session_id), json.dumps({"frame": encoded}))


async def subscribe_frames(session_id: str) -> PubSub:
    """Subscribe to the Redis channel that carries frames for a session."""

    return await subscribe(_frame_channel(session_id))


async def close_frame_subscription(pubsub: PubSub) -> None:
    """Unsubscribe and close a pubsub client."""

    try:
        await pubsub.unsubscribe()
    finally:
        await pubsub.close()


def decode_frame_message(message: str) -> bytes:
    """Decode a frame payload published by :func:`publish_frame`."""

    data = json.loads(message)
    frame_value = data.get("frame", "")
    return base64.b64decode(frame_value)
