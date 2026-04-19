"""RL Training Agent — orchestrates parallel environments, experience collection, and training.

Provides:
- TrainingConfig / CheckpointMetadata / ExperienceBatch schemas
- create_parallel_envs() — vectorized environment wrapper
- collect_experiences() — gather transitions from parallel envs
- ReplayBuffer — experience storage and sampling
- save_checkpoint() / load_checkpoint() / list_checkpoints() — model persistence
- persist_training_metrics() / get_training_metrics() — Redis state
"""
from __future__ import annotations

import asyncio
import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

from co_sim.core.redis import get_redis


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TrainingConfig(BaseModel):
    """Configuration for RL training run."""

    workspace_id: str
    algorithm: str = Field(..., pattern=r"^(PPO|SAC|TD3|DQN)$")
    environment: str  # e.g. "MuJoCo-Hopper-v4" or "CartPole-v1"
    total_timesteps: int = Field(gt=0)
    n_envs: int = Field(default=4, gt=0)
    learning_rate: float = Field(default=3e-4, gt=0, lt=1)
    batch_size: int = Field(default=64, gt=0)
    gamma: float = Field(default=0.99, ge=0, le=1)


class CheckpointMetadata(BaseModel):
    """Metadata for a training checkpoint."""

    run_id: str
    timestep: int = Field(gt=0)
    episode: int = Field(ge=0)
    mean_reward: float
    model_path: str
    optimizer_state_path: str = ""


class ExperienceBatch(BaseModel):
    """Batch of experience transitions."""

    observations: List[List[float]]
    actions: List[List[int]]
    rewards: List[float]
    next_observations: List[List[float]]
    dones: List[bool]


# ---------------------------------------------------------------------------
# Parallel Environment Wrapper
# ---------------------------------------------------------------------------

class ParallelEnvWrapper:
    """Wrapper for vectorized parallel environments."""

    def __init__(self, env_id: str, n_envs: int, seed: int = 42):
        """Initialize parallel environments.

        In a production system, this would use gym.vector or similar.
        For testing, we use a simple mock implementation.
        """
        self.env_id = env_id
        self.num_envs = n_envs
        self.seed = seed
        self._rng = np.random.RandomState(seed)

        # Mock observation and action spaces
        # In real implementation, these would come from gym.make(env_id)
        if "CartPole" in env_id:
            self.observation_space = MockSpace(shape=(4,), dtype=np.float32)
            self.action_space = MockSpace(n=2, dtype=np.int64)
        else:
            # Generic continuous control
            self.observation_space = MockSpace(shape=(11,), dtype=np.float32)
            self.action_space = MockSpace(shape=(3,), dtype=np.float32)

        self._current_obs = None

    async def reset(self) -> List[np.ndarray]:
        """Reset all parallel environments."""
        if "CartPole" in self.env_id:
            obs_shape = (4,)
        else:
            obs_shape = (11,)

        self._current_obs = [
            self._rng.randn(*obs_shape).astype(np.float32)
            for _ in range(self.num_envs)
        ]
        return self._current_obs

    async def step(self, actions: List[Any]) -> tuple:
        """Execute actions in all parallel environments."""
        assert len(actions) == self.num_envs, \
            f"Expected {self.num_envs} actions, got {len(actions)}"

        # Mock step: random next observations and rewards
        if "CartPole" in self.env_id:
            obs_shape = (4,)
        else:
            obs_shape = (11,)

        next_obs = [
            self._rng.randn(*obs_shape).astype(np.float32)
            for _ in range(self.num_envs)
        ]

        rewards = [float(self._rng.randn()) for _ in range(self.num_envs)]
        dones = [self._rng.rand() < 0.05 for _ in range(self.num_envs)]  # 5% done prob
        infos = [{} for _ in range(self.num_envs)]

        self._current_obs = next_obs
        return next_obs, rewards, dones, infos


class MockSpace:
    """Mock gym space for testing."""

    def __init__(self, shape=None, n=None, dtype=np.float32):
        self.shape = shape
        self.n = n
        self.dtype = dtype

    def sample(self):
        """Sample random action."""
        if self.n is not None:
            return np.random.randint(0, self.n)
        elif self.shape is not None:
            return np.random.randn(*self.shape).astype(self.dtype)
        return 0


async def create_parallel_envs(
    env_id: str,
    n_envs: int,
    seed: int = 42,
) -> ParallelEnvWrapper:
    """Create parallel environment wrapper for vectorized training."""
    return ParallelEnvWrapper(env_id, n_envs, seed)


# ---------------------------------------------------------------------------
# Experience Collection
# ---------------------------------------------------------------------------

async def collect_experiences(
    env_wrapper: ParallelEnvWrapper,
    policy: Callable,
    n_steps: int,
) -> ExperienceBatch:
    """Collect experiences from parallel environments using a policy.

    Args:
        env_wrapper: Parallel environment wrapper
        policy: Function that takes observations and returns actions
        n_steps: Number of steps to collect per environment

    Returns:
        ExperienceBatch with collected transitions
    """
    observations = []
    actions = []
    rewards = []
    next_observations = []
    dones = []

    current_obs = env_wrapper._current_obs
    if current_obs is None:
        current_obs = await env_wrapper.reset()

    for _ in range(n_steps):
        # Get actions from policy
        action_list = policy(current_obs)

        # Step environments
        next_obs, reward_list, done_list, _ = await env_wrapper.step(action_list)

        # Store transitions
        for i in range(env_wrapper.num_envs):
            observations.append(current_obs[i].tolist() if isinstance(current_obs[i], np.ndarray) else current_obs[i])

            # Handle both scalar and array actions
            if isinstance(action_list[i], (int, float)):
                actions.append([int(action_list[i])])
            else:
                actions.append([int(a) for a in action_list[i]])

            rewards.append(float(reward_list[i]))
            next_observations.append(next_obs[i].tolist() if isinstance(next_obs[i], np.ndarray) else next_obs[i])
            dones.append(done_list[i])

        current_obs = next_obs

    return ExperienceBatch(
        observations=observations,
        actions=actions,
        rewards=rewards,
        next_observations=next_observations,
        dones=dones,
    )


# ---------------------------------------------------------------------------
# Replay Buffer
# ---------------------------------------------------------------------------

class ReplayBuffer:
    """Experience replay buffer for off-policy algorithms."""

    def __init__(self, capacity: int = 100000):
        self.capacity = capacity
        self._buffer: List[Dict[str, Any]] = []
        self._position = 0

    def store(
        self,
        observation: Any,
        action: Any,
        reward: float,
        next_observation: Any,
        done: bool,
    ):
        """Store a single transition."""
        transition = {
            "observation": observation,
            "action": action,
            "reward": reward,
            "next_observation": next_observation,
            "done": done,
        }

        if len(self._buffer) < self.capacity:
            self._buffer.append(transition)
        else:
            self._buffer[self._position] = transition

        self._position = (self._position + 1) % self.capacity

    def sample(self, batch_size: int) -> ExperienceBatch:
        """Sample a random batch of transitions."""
        indices = np.random.randint(0, len(self._buffer), size=batch_size)

        observations = []
        actions = []
        rewards = []
        next_observations = []
        dones = []

        for idx in indices:
            transition = self._buffer[idx]
            observations.append(transition["observation"])
            actions.append(transition["action"])
            rewards.append(transition["reward"])
            next_observations.append(transition["next_observation"])
            dones.append(transition["done"])

        return ExperienceBatch(
            observations=observations,
            actions=actions,
            rewards=rewards,
            next_observations=next_observations,
            dones=dones,
        )

    def size(self) -> int:
        """Return current buffer size."""
        return len(self._buffer)


# ---------------------------------------------------------------------------
# Checkpoint Management
# ---------------------------------------------------------------------------

async def save_checkpoint(
    run_id: str,
    timestep: int,
    episode: int,
    mean_reward: float,
    model_state: Dict[str, Any],
    optimizer_state: Dict[str, Any],
    checkpoint_dir: str = "/tmp/cosim/checkpoints",
) -> CheckpointMetadata:
    """Save training checkpoint to disk.

    Args:
        run_id: Unique identifier for training run
        timestep: Current training timestep
        episode: Current episode number
        mean_reward: Mean episode reward
        model_state: Model weights and architecture
        optimizer_state: Optimizer state dict
        checkpoint_dir: Root directory for checkpoints

    Returns:
        CheckpointMetadata with paths to saved files
    """
    checkpoint_path = Path(checkpoint_dir) / run_id
    checkpoint_path.mkdir(parents=True, exist_ok=True)

    # Save model
    model_path = checkpoint_path / f"step_{timestep}.zip"
    with open(model_path, "wb") as f:
        pickle.dump(model_state, f)

    # Save optimizer state
    optimizer_path = checkpoint_path / f"optimizer_{timestep}.pt"
    with open(optimizer_path, "wb") as f:
        pickle.dump(optimizer_state, f)

    # Save metadata
    metadata = CheckpointMetadata(
        run_id=run_id,
        timestep=timestep,
        episode=episode,
        mean_reward=mean_reward,
        model_path=str(model_path),
        optimizer_state_path=str(optimizer_path),
    )

    metadata_path = checkpoint_path / f"metadata_{timestep}.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata.model_dump(), f, indent=2)

    return metadata


async def load_checkpoint(
    run_id: str,
    checkpoint_dir: str = "/tmp/cosim/checkpoints",
    timestep: Optional[int] = None,
) -> tuple[CheckpointMetadata, Dict[str, Any], Dict[str, Any]]:
    """Load training checkpoint from disk.

    Args:
        run_id: Unique identifier for training run
        checkpoint_dir: Root directory for checkpoints
        timestep: Specific timestep to load (if None, loads latest)

    Returns:
        Tuple of (metadata, model_state, optimizer_state)
    """
    checkpoint_path = Path(checkpoint_dir) / run_id

    # Find checkpoint files
    if timestep is None:
        # Load latest checkpoint
        metadata_files = sorted(checkpoint_path.glob("metadata_*.json"))
        if not metadata_files:
            raise FileNotFoundError(f"No checkpoints found for run {run_id}")
        metadata_file = metadata_files[-1]
    else:
        metadata_file = checkpoint_path / f"metadata_{timestep}.json"

    # Load metadata
    with open(metadata_file) as f:
        metadata_dict = json.load(f)
    metadata = CheckpointMetadata(**metadata_dict)

    # Load model
    with open(metadata.model_path, "rb") as f:
        model_state = pickle.load(f)

    # Load optimizer
    with open(metadata.optimizer_state_path, "rb") as f:
        optimizer_state = pickle.load(f)

    return metadata, model_state, optimizer_state


async def list_checkpoints(
    run_id: str,
    checkpoint_dir: str = "/tmp/cosim/checkpoints",
) -> List[CheckpointMetadata]:
    """List all checkpoints for a training run.

    Args:
        run_id: Unique identifier for training run
        checkpoint_dir: Root directory for checkpoints

    Returns:
        List of CheckpointMetadata sorted by timestep
    """
    checkpoint_path = Path(checkpoint_dir) / run_id

    if not checkpoint_path.exists():
        return []

    checkpoints = []
    for metadata_file in sorted(checkpoint_path.glob("metadata_*.json")):
        with open(metadata_file) as f:
            metadata_dict = json.load(f)
        checkpoints.append(CheckpointMetadata(**metadata_dict))

    return sorted(checkpoints, key=lambda x: x.timestep)


# ---------------------------------------------------------------------------
# Training State Persistence (Redis)
# ---------------------------------------------------------------------------

async def persist_training_metrics(
    run_id: str,
    timestep: int,
    episode: int,
    mean_reward: float,
    episode_length: Optional[int] = None,
):
    """Persist training metrics to Redis for monitoring.

    Args:
        run_id: Unique identifier for training run
        timestep: Current training timestep
        episode: Current episode number
        mean_reward: Mean episode reward
        episode_length: Mean episode length (optional)
    """
    redis = await get_redis()

    metrics = {
        "timestep": timestep,
        "episode": episode,
        "mean_reward": mean_reward,
    }

    if episode_length is not None:
        metrics["episode_length"] = episode_length

    key = f"rl_training:{run_id}:metrics"
    await redis.set(key, json.dumps(metrics))

    # Also store in a sorted set for time-series queries
    await redis.zadd(
        f"rl_training:{run_id}:history",
        {json.dumps(metrics): timestep}
    )


async def get_training_metrics(run_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve current training metrics from Redis.

    Args:
        run_id: Unique identifier for training run

    Returns:
        Dictionary of current metrics, or None if not found
    """
    redis = await get_redis()
    key = f"rl_training:{run_id}:metrics"

    data = await redis.get(key)
    if data is None:
        return None

    return json.loads(data)
