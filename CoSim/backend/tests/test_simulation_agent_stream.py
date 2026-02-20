from __future__ import annotations

import asyncio
import contextlib

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient

from co_sim.core import redis as redis_helpers


class FakeStreamManager:
    def __init__(self) -> None:
        self.is_streaming = False
        self._task: asyncio.Task | None = None
        self._frame = 0

    def get_state(self) -> dict[str, float | int]:
        return {"frame": self._frame, "time": float(self._frame)}

    def reset(self) -> dict[str, float | int]:
        self._frame = 0
        return self.get_state()

    def step(self, actions=None) -> dict[str, float | int]:  # pragma: no cover - not exercised
        self._frame += 1
        return self.get_state()

    async def start_streaming(self, frame_callback, state_callback=None) -> None:
        if self.is_streaming:
            return
        self.is_streaming = True

        async def _loop() -> None:
            for _ in range(2):
                self._frame += 1
                await frame_callback(f"frame-{self._frame}".encode("utf-8"))
                if state_callback:
                    result = state_callback(self.get_state())
                    if asyncio.iscoroutine(result):
                        await result
                await asyncio.sleep(0.01)

        self._task = asyncio.create_task(_loop())

    async def stop_streaming(self) -> None:
        self.is_streaming = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def close(self) -> None:
        return


@pytest.fixture()
def _fake_redis() -> None:
    asyncio.run(redis_helpers.reset_redis_state())
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    yield
    asyncio.run(redis_helpers.reset_redis_state())


def test_simulation_stream_websocket(_fake_redis, monkeypatch) -> None:
    from co_sim.agents.simulation import main as sim_main

    sim_main.simulations.clear()
    monkeypatch.setattr(sim_main, "_create_manager", lambda _: FakeStreamManager())
    monkeypatch.setattr(sim_main.settings, "webrtc_enabled", False)
    monkeypatch.setattr(sim_main.settings, "webrtc_signaling_url", "")

    with TestClient(sim_main.app) as client:
        response = client.post(
            "/simulations/create",
            json={
                "session_id": "sim-test",
                "engine": "mujoco",
                "model_path": "/tmp/fake.xml",
            },
        )
        assert response.status_code == 200

        with client.websocket_connect("/simulations/sim-test/stream") as websocket:
            payload = websocket.receive_bytes()
            assert payload.startswith(b"frame-")
