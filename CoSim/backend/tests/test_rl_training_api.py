"""Tests for the RL Training Agent API endpoints.

TDD: These tests verify the API integration for RL training.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import AsyncClient, ASGITransport

from co_sim.core import redis as redis_helpers


@pytest_asyncio.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


@pytest_asyncio.fixture
async def client():
    """Create test client for simulation agent."""
    from co_sim.agents.simulation.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_start_rl_training_endpoint(client):
    """POST /rl/train starts an RL training run."""
    payload = {
        "workspace_id": "ws-1",
        "algorithm": "PPO",
        "environment": "CartPole-v1",
        "total_timesteps": 1000,
        "n_envs": 2,
        "learning_rate": 0.0003,
        "batch_size": 64,
        "gamma": 0.99,
    }

    response = await client.post("/rl/train", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "started"
    assert "run_id" in data
    assert data["config"]["algorithm"] == "PPO"
    assert data["env_info"]["num_envs"] == 2


@pytest.mark.asyncio
async def test_start_rl_training_with_custom_run_id(client):
    """POST /rl/train accepts custom run_id."""
    payload = {
        "run_id": "custom-run-123",
        "workspace_id": "ws-2",
        "algorithm": "SAC",
        "environment": "MuJoCo-Hopper-v4",
        "total_timesteps": 5000,
        "n_envs": 4,
    }

    response = await client.post("/rl/train", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["run_id"] == "custom-run-123"


@pytest.mark.asyncio
async def test_start_rl_training_invalid_config(client):
    """POST /rl/train rejects invalid configuration."""
    payload = {
        "workspace_id": "ws-3",
        "algorithm": "INVALID_ALGO",  # Invalid algorithm
        "environment": "CartPole-v1",
        "total_timesteps": 1000,
    }

    response = await client.post("/rl/train", json=payload)
    assert response.status_code == 200  # Returns error in body, not HTTP error

    data = response.json()
    assert data["status"] == "error"
    assert "Invalid training config" in data["error"]


@pytest.mark.asyncio
async def test_get_rl_metrics_endpoint(client):
    """GET /rl/runs/{run_id}/metrics returns training metrics."""
    # First, start a training run
    payload = {
        "run_id": "metrics-test-run",
        "workspace_id": "ws-4",
        "algorithm": "PPO",
        "environment": "CartPole-v1",
        "total_timesteps": 1000,
        "n_envs": 2,
    }

    start_response = await client.post("/rl/train", json=payload)
    assert start_response.status_code == 200

    # Now get metrics
    metrics_response = await client.get("/rl/runs/metrics-test-run/metrics")
    assert metrics_response.status_code == 200

    metrics = metrics_response.json()
    assert metrics["timestep"] == 0
    assert metrics["episode"] == 0
    assert metrics["mean_reward"] == 0.0


@pytest.mark.asyncio
async def test_get_rl_metrics_not_found(client):
    """GET /rl/runs/{run_id}/metrics returns 404 for non-existent run."""
    response = await client.get("/rl/runs/non-existent-run/metrics")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_rl_checkpoints_endpoint(client):
    """GET /rl/runs/{run_id}/checkpoints returns checkpoint list."""
    response = await client.get("/rl/runs/test-run/checkpoints")
    assert response.status_code == 200

    data = response.json()
    assert data["run_id"] == "test-run"
    assert "checkpoints" in data
    assert isinstance(data["checkpoints"], list)


@pytest.mark.asyncio
async def test_rl_training_workflow(client):
    """Complete workflow: start training, check metrics, list checkpoints."""
    # 1. Start training
    payload = {
        "run_id": "workflow-test",
        "workspace_id": "ws-workflow",
        "algorithm": "PPO",
        "environment": "CartPole-v1",
        "total_timesteps": 2000,
        "n_envs": 4,
    }

    start_response = await client.post("/rl/train", json=payload)
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "started"

    # 2. Get metrics
    metrics_response = await client.get("/rl/runs/workflow-test/metrics")
    assert metrics_response.status_code == 200

    # 3. List checkpoints
    checkpoints_response = await client.get("/rl/runs/workflow-test/checkpoints")
    assert checkpoints_response.status_code == 200
    assert checkpoints_response.json()["run_id"] == "workflow-test"
