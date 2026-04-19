# PyBullet PPO Training Template

This template provides a complete setup for training a PPO (Proximal Policy Optimization) agent on PyBullet environments using the CoSim platform.

## Overview

- **Algorithm**: PPO
- **Environment**: CartPole-v1 (can be changed to any PyBullet env)
- **Framework**: CoSim RL Training Agent
- **Features**:
  - Parallel environment vectorization (4 envs by default)
  - Automatic checkpoint management
  - Redis-backed metrics tracking
  - Experience replay buffer

## Quick Start

```bash
# Run training
python train_ppo.py
```

## Configuration

Edit `train_ppo.py` to customize:

```python
config = {
    "workspace_id": "your-workspace-id",
    "algorithm": "PPO",
    "environment": "CartPole-v1",  # Or any PyBullet env
    "total_timesteps": 50000,
    "n_envs": 4,                   # Number of parallel environments
    "learning_rate": 0.0003,
    "batch_size": 64,
    "gamma": 0.99,                 # Discount factor
}
```

## Monitoring

### View Training Metrics

```bash
curl http://localhost:8000/rl/runs/{run_id}/metrics
```

Response:
```json
{
  "timestep": 10000,
  "episode": 500,
  "mean_reward": 195.5
}
```

### List Checkpoints

```bash
curl http://localhost:8000/rl/runs/{run_id}/checkpoints
```

Response:
```json
{
  "run_id": "run-abc123",
  "checkpoints": [
    {
      "timestep": 10000,
      "episode": 500,
      "mean_reward": 150.0,
      "model_path": "/checkpoints/run-abc123/step_10000.zip"
    }
  ]
}
```

## Supported Environments

- **CartPole-v1**: Balance a pole on a cart
- **Pendulum-v1**: Swing up an inverted pendulum
- **LunarLander-v2**: Land a spacecraft
- **BipedalWalker-v3**: Teach a 2D robot to walk
- **Custom PyBullet envs**: Load your own URDF models

## Hyperparameter Tuning

### PPO Hyperparameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `learning_rate` | 0.0003 | Learning rate for policy and value networks |
| `gamma` | 0.99 | Discount factor for future rewards |
| `batch_size` | 64 | Mini-batch size for policy updates |
| `n_envs` | 4 | Number of parallel environments |

### Recommended Values

**For discrete action spaces (CartPole, Lunar Lander):**
- `learning_rate`: 0.0003 - 0.001
- `gamma`: 0.99
- `batch_size`: 64

**For continuous action spaces (Pendulum, BipedalWalker):**
- `learning_rate`: 0.0001 - 0.0003
- `gamma`: 0.99
- `batch_size`: 128

## Next Steps

1. **Custom Environment**: Replace CartPole with your own PyBullet URDF model
2. **Hyperparameter Search**: Experiment with different learning rates and batch sizes
3. **Checkpoint Loading**: Load trained checkpoints for evaluation
4. **Multi-agent Training**: Scale to multiple parallel runs

## API Reference

See the [RL Training Agent API documentation](../../../docs/rl-training-api.md) for complete endpoint details.
