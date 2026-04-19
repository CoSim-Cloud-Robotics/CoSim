# MuJoCo PPO Training Template

This template provides a complete setup for training PPO agents on MuJoCo physics simulation environments.

## Overview

- **Algorithm**: PPO (Proximal Policy Optimization)
- **Environment**: MuJoCo Hopper-v4 (configurable)
- **Framework**: CoSim RL Training Agent
- **Features**:
  - Parallel environment vectorization (8 envs by default)
  - Automatic checkpoint management every 50k steps
  - Real-time metrics tracking via Redis
  - GPU acceleration support (when available)

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
    "environment": "MuJoCo-Hopper-v4",
    "total_timesteps": 1000000,    # 1M steps for MuJoCo
    "n_envs": 8,                   # Parallel environments
    "learning_rate": 0.0003,
    "batch_size": 128,
    "gamma": 0.99,
}
```

## Supported MuJoCo Environments

| Environment | Description | Action Space | Difficulty |
|-------------|-------------|--------------|------------|
| `Hopper-v4` | 2D one-legged robot | 3 continuous | Medium |
| `Walker2d-v4` | 2D bipedal walker | 6 continuous | Hard |
| `HalfCheetah-v4` | 2D running robot | 6 continuous | Medium |
| `Ant-v4` | 3D quadruped robot | 8 continuous | Hard |
| `Humanoid-v4` | 3D humanoid robot | 17 continuous | Very Hard |

## Training Progress

### Expected Performance

**Hopper-v4:**
- Initial reward: ~0-50
- After 100k steps: ~500-1000
- After 500k steps: ~2000-3000
- After 1M steps: ~3000+ (solved)

**Walker2d-v4:**
- Initial reward: ~0-50
- After 1M steps: ~3000-4000 (solved)

## Hyperparameters

### Default Values (Hopper)

```python
{
    "learning_rate": 0.0003,
    "n_envs": 8,
    "batch_size": 128,
    "gamma": 0.99,
    "total_timesteps": 1000000
}
```

### For Humanoid (harder task)

```python
{
    "learning_rate": 0.0001,    # Lower LR for stability
    "n_envs": 16,               # More parallel envs
    "batch_size": 256,          # Larger batches
    "gamma": 0.99,
    "total_timesteps": 10000000 # 10M steps
}
```

## Monitoring Training

### Real-time Metrics

```bash
# Get current metrics
curl http://localhost:8000/rl/runs/{run_id}/metrics
```

Response:
```json
{
  "timestep": 250000,
  "episode": 5000,
  "mean_reward": 1523.4,
  "episode_length": 500
}
```

### Checkpoints

```bash
# List all checkpoints
curl http://localhost:8000/rl/runs/{run_id}/checkpoints
```

## Advanced Usage

### Multi-Environment Training

Train on multiple environments simultaneously:

```python
configs = [
    {"environment": "Hopper-v4", "run_id": "hopper-run-1"},
    {"environment": "Walker2d-v4", "run_id": "walker-run-1"},
    {"environment": "HalfCheetah-v4", "run_id": "cheetah-run-1"},
]

for config in configs:
    requests.post("http://localhost:8000/rl/train", json=config)
```

### Resume from Checkpoint

```python
# Load checkpoint and continue training
checkpoint = requests.get(
    f"http://localhost:8000/rl/runs/{run_id}/checkpoints"
).json()["checkpoints"][-1]

# Use checkpoint model_path to resume
```

## GPU Scheduling

For GPU-accelerated training, ensure GPU resources are allocated:

```python
config = {
    # ... other config ...
    "gpu": True,
    "gpu_memory_limit": "4GB",
}
```

See [GPU Scheduling Guide](../../../docs/gpu-scheduling.md) for details.

## Troubleshooting

### Training is unstable

- Reduce learning rate: `0.0001` instead of `0.0003`
- Increase batch size: `256` instead of `128`
- Adjust gamma: Try `0.95` for shorter-horizon tasks

### Training is too slow

- Increase parallel environments: `16` or `32` instead of `8`
- Use GPU acceleration
- Reduce total timesteps for initial experiments

## Next Steps

1. **Hyperparameter tuning**: Try different learning rates
2. **Environment customization**: Load custom MuJoCo XML models
3. **Algorithm comparison**: Compare with SAC or TD3
4. **Transfer learning**: Fine-tune on related tasks

## References

- [MuJoCo Documentation](https://mujoco.readthedocs.io/)
- [PPO Paper](https://arxiv.org/abs/1707.06347)
- [Stable-Baselines3 Docs](https://stable-baselines3.readthedocs.io/)
