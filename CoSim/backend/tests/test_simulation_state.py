from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from co_sim.core import redis as redis_helpers
from co_sim.services import simulation_state


@pytest_asyncio.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


@pytest.mark.asyncio
async def test_simulation_persistence_roundtrip():
    config = simulation_state.SimulationConfig(
        session_id="sim-123",
        engine="pybullet",
        model_path="/tmp/model.urdf",
    )

    await simulation_state.persist_config(config)

    assert await simulation_state.list_session_ids() == [config.session_id]
    loaded = await simulation_state.get_config(config.session_id)
    assert loaded == config

    state_payload = {"frame": 5, "time": 0.25, "status": "stepped"}
    await simulation_state.update_state(
        config.session_id,
        state_payload,
        status="stepped",
        streaming=False,
    )

    stored_state = await simulation_state.get_state(config.session_id)
    assert stored_state is not None
    assert stored_state.frame == 5
    assert stored_state.data["status"] == "stepped"

    await simulation_state.remove_simulation(config.session_id)
    assert await simulation_state.list_session_ids() == []


@pytest.mark.asyncio
async def test_frame_pubsub_roundtrip():
    session_id = "sim-stream"
    pubsub = await simulation_state.subscribe_frames(session_id)

    try:
        await simulation_state.publish_frame(session_id, b"frame-data")
        received = None
        for _ in range(20):
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("data"):
                received = simulation_state.decode_frame_message(message["data"])
                break
            await asyncio.sleep(0.05)

        assert received == b"frame-data"
    finally:
        await simulation_state.close_frame_subscription(pubsub)
