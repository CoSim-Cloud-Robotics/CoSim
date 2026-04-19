"""Tests for the RL Training Agent service layer and API.

TDD: These tests define the expected behaviour of the RL training agent
before the implementation exists.
"""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from co_sim.core import redis as redis_helpers


@pytest_asyncio.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_training_config_schema():
    """TrainingConfig validates required fields for RL training."""
    from co_sim.services.rl_training_agent import TrainingConfig

    config = TrainingConfig(
        workspace_id="ws-1",
        algorithm="PPO",
        environment="MuJoCo-Hopper-v4",
        total_timesteps=100000,
        n_envs=4,
        learning_rate=3e-4,
        batch_size=64,
        gamma=0.99,
    )
    assert config.algorithm in ("PPO", "SAC", "TD3", "DQN")
    assert config.n_envs > 0
    assert 0 < config.learning_rate < 1
    assert 0 <= config.gamma <= 1


@pytest.mark.asyncio
async def test_checkpoint_metadata_schema():
    """CheckpointMetadata captures training progress and model state."""
    from co_sim.services.rl_training_agent import CheckpointMetadata

    metadata = CheckpointMetadata(
        run_id="run-abc",
        timestep=50000,
        episode=1000,
        mean_reward=250.5,
        model_path="/checkpoints/run-abc/step_50000.zip",
        optimizer_state_path="/checkpoints/run-abc/optimizer_50000.pt",
    )
    assert metadata.timestep > 0
    assert metadata.mean_reward > 0
    assert metadata.model_path.endswith(".zip")


@pytest.mark.asyncio
async def test_experience_batch_schema():
    """ExperienceBatch stores collected transitions."""
    from co_sim.services.rl_training_agent import ExperienceBatch

    batch = ExperienceBatch(
        observations=[[0.1, 0.2], [0.3, 0.4]],
        actions=[[1], [0]],
        rewards=[1.0, -0.5],
        next_observations=[[0.2, 0.3], [0.4, 0.5]],
        dones=[False, True],
    )
    assert len(batch.observations) == len(batch.actions)
    assert len(batch.rewards) == len(batch.dones)


# ---------------------------------------------------------------------------
# Parallel environment orchestration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_parallel_envs():
    """Create multiple parallel environments for vectorized training."""
    from co_sim.services.rl_training_agent import create_parallel_envs

    env_wrapper = await create_parallel_envs(
        env_id="CartPole-v1",
        n_envs=4,
        seed=42,
    )
    assert env_wrapper.num_envs == 4
    assert env_wrapper.observation_space is not None
    assert env_wrapper.action_space is not None


@pytest.mark.asyncio
async def test_parallel_env_reset():
    """Parallel environments can be reset."""
    from co_sim.services.rl_training_agent import create_parallel_envs

    env_wrapper = await create_parallel_envs("CartPole-v1", n_envs=2, seed=42)
    observations = await env_wrapper.reset()

    assert len(observations) == 2  # 2 parallel envs
    assert all(isinstance(obs, (list, np.ndarray)) for obs in observations)


@pytest.mark.asyncio
async def test_parallel_env_step():
    """Parallel environments can execute actions."""
    from co_sim.services.rl_training_agent import create_parallel_envs

    env_wrapper = await create_parallel_envs("CartPole-v1", n_envs=2, seed=42)
    await env_wrapper.reset()

    actions = [1, 0]  # Actions for 2 envs
    observations, rewards, dones, infos = await env_wrapper.step(actions)

    assert len(observations) == 2
    assert len(rewards) == 2
    assert len(dones) == 2
    assert isinstance(rewards[0], (int, float))


# ---------------------------------------------------------------------------
# Experience collection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collect_experiences():
    """Collect experiences from parallel environments."""
    from co_sim.services.rl_training_agent import (
        create_parallel_envs,
        collect_experiences,
    )

    env_wrapper = await create_parallel_envs("CartPole-v1", n_envs=2, seed=42)

    # Simple random policy for testing
    def random_policy(obs):
        return [env_wrapper.action_space.sample() for _ in range(len(obs))]

    batch = await collect_experiences(
        env_wrapper=env_wrapper,
        policy=random_policy,
        n_steps=10,
    )

    assert len(batch.observations) == 20  # 2 envs * 10 steps
    assert len(batch.rewards) == 20
    assert all(isinstance(r, (int, float)) for r in batch.rewards)


@pytest.mark.asyncio
async def test_replay_buffer_store_and_sample():
    """ReplayBuffer stores transitions and samples batches."""
    from co_sim.services.rl_training_agent import ReplayBuffer

    buffer = ReplayBuffer(capacity=1000)

    # Store some transitions
    for i in range(100):
        buffer.store(
            observation=[i, i+1],
            action=[0],
            reward=1.0,
            next_observation=[i+1, i+2],
            done=False,
        )

    assert buffer.size() == 100

    # Sample a batch
    batch = buffer.sample(batch_size=32)
    assert len(batch.observations) == 32
    assert len(batch.actions) == 32


# ---------------------------------------------------------------------------
# Checkpoint management tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_checkpoint(tmp_path):
    """Save model checkpoint with metadata."""
    from co_sim.services.rl_training_agent import save_checkpoint

    # Mock model state
    model_state = {"policy": "dummy_weights", "value": "dummy_weights"}
    optimizer_state = {"lr": 0.001}

    metadata = await save_checkpoint(
        run_id="run-test",
        timestep=1000,
        episode=50,
        mean_reward=100.5,
        model_state=model_state,
        optimizer_state=optimizer_state,
        checkpoint_dir=str(tmp_path),
    )

    assert metadata.timestep == 1000
    assert metadata.episode == 50
    assert metadata.mean_reward == 100.5
    assert (tmp_path / "run-test").exists()


@pytest.mark.asyncio
async def test_load_checkpoint(tmp_path):
    """Load model checkpoint and restore training state."""
    from co_sim.services.rl_training_agent import save_checkpoint, load_checkpoint

    model_state = {"policy": "weights_v1"}
    optimizer_state = {"lr": 0.001}

    # Save checkpoint
    saved_metadata = await save_checkpoint(
        run_id="run-restore",
        timestep=5000,
        episode=250,
        mean_reward=200.0,
        model_state=model_state,
        optimizer_state=optimizer_state,
        checkpoint_dir=str(tmp_path),
    )

    # Load checkpoint
    loaded_metadata, loaded_model, loaded_optimizer = await load_checkpoint(
        run_id="run-restore",
        checkpoint_dir=str(tmp_path),
    )

    assert loaded_metadata.timestep == 5000
    assert loaded_metadata.episode == 250
    assert loaded_model["policy"] == "weights_v1"
    assert loaded_optimizer["lr"] == 0.001


@pytest.mark.asyncio
async def test_list_checkpoints(tmp_path):
    """List all checkpoints for a given run."""
    from co_sim.services.rl_training_agent import save_checkpoint, list_checkpoints

    # Save multiple checkpoints
    for step in [1000, 2000, 3000]:
        await save_checkpoint(
            run_id="run-multi",
            timestep=step,
            episode=step // 20,
            mean_reward=step / 10,
            model_state={"step": step},
            optimizer_state={},
            checkpoint_dir=str(tmp_path),
        )

    checkpoints = await list_checkpoints("run-multi", str(tmp_path))
    assert len(checkpoints) == 3
    assert checkpoints[0].timestep == 1000
    assert checkpoints[-1].timestep == 3000


# ---------------------------------------------------------------------------
# Training state persistence in Redis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_training_state_in_redis():
    """Training metrics are persisted to Redis for monitoring."""
    from co_sim.services.rl_training_agent import (
        persist_training_metrics,
        get_training_metrics,
    )

    await persist_training_metrics(
        run_id="run-1",
        timestep=1000,
        episode=50,
        mean_reward=150.0,
        episode_length=200,
    )

    metrics = await get_training_metrics("run-1")
    assert metrics is not None
    assert metrics["timestep"] == 1000
    assert metrics["mean_reward"] == 150.0


@pytest.mark.asyncio
async def test_update_training_progress():
    """Training progress updates are tracked."""
    from co_sim.services.rl_training_agent import (
        persist_training_metrics,
        get_training_metrics,
    )

    # Initial state
    await persist_training_metrics("run-2", timestep=100, episode=5, mean_reward=10.0)

    # Update progress
    await persist_training_metrics("run-2", timestep=500, episode=25, mean_reward=50.0)

    metrics = await get_training_metrics("run-2")
    assert metrics["timestep"] == 500
    assert metrics["episode"] == 25
    assert metrics["mean_reward"] == 50.0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_training_run_end_to_end(tmp_path):
    """Complete training run: env setup, experience collection, checkpoint saving."""
    from co_sim.services.rl_training_agent import (
        TrainingConfig,
        create_parallel_envs,
        collect_experiences,
        save_checkpoint,
        persist_training_metrics,
    )

    config = TrainingConfig(
        workspace_id="ws-e2e",
        algorithm="PPO",
        environment="CartPole-v1",
        total_timesteps=1000,
        n_envs=2,
        learning_rate=3e-4,
        batch_size=64,
        gamma=0.99,
    )

    # Create environments
    env_wrapper = await create_parallel_envs(
        config.environment,
        n_envs=config.n_envs,
        seed=42,
    )

    # Random policy for testing
    def random_policy(obs):
        return [env_wrapper.action_space.sample() for _ in range(len(obs))]

    # Collect some experiences
    batch = await collect_experiences(env_wrapper, random_policy, n_steps=10)
    assert len(batch.observations) > 0

    # Save checkpoint
    metadata = await save_checkpoint(
        run_id="run-e2e",
        timestep=100,
        episode=5,
        mean_reward=20.0,
        model_state={"test": "data"},
        optimizer_state={},
        checkpoint_dir=str(tmp_path),
    )

    # Persist metrics
    await persist_training_metrics(
        run_id="run-e2e",
        timestep=100,
        episode=5,
        mean_reward=20.0,
    )

    assert metadata.mean_reward == 20.0
