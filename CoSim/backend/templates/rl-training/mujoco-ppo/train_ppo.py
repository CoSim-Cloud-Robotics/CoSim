"""MuJoCo PPO Training Template

This template demonstrates how to train a PPO agent on MuJoCo environments
using the CoSim RL training infrastructure.

Usage:
    python train_ppo.py
"""
import asyncio
import requests


async def main():
    """Train PPO agent on MuJoCo Hopper."""

    # Configure training run
    config = {
        "workspace_id": "mujoco-ppo-demo",
        "algorithm": "PPO",
        "environment": "MuJoCo-Hopper-v4",
        "total_timesteps": 1000000,  # MuJoCo tasks need more steps
        "n_envs": 8,  # More parallel environments for faster training
        "learning_rate": 0.0003,
        "batch_size": 128,
        "gamma": 0.99,
    }

    print("Starting PPO training on MuJoCo Hopper...")
    print(f"Algorithm: {config['algorithm']}")
    print(f"Environment: {config['environment']}")
    print(f"Total timesteps: {config['total_timesteps']:,}")
    print(f"Parallel envs: {config['n_envs']}")
    print()

    # Start training via API
    response = requests.post(
        "http://localhost:8000/rl/train",
        json=config
    )

    if response.status_code == 200:
        result = response.json()

        if result["status"] == "started":
            run_id = result["run_id"]
            print(f"✅ Training started successfully!")
            print(f"Run ID: {run_id}")
            print(f"Environment info: {result['env_info']}")
            print()

            print("Training MuJoCo environments typically takes longer.")
            print("Expected training time: 1-2 hours")
            print()

            # Monitor training progress
            print("Monitor progress with:")
            print(f"  curl http://localhost:8000/rl/runs/{run_id}/metrics")
            print()
            print("List checkpoints with:")
            print(f"  curl http://localhost:8000/rl/runs/{run_id}/checkpoints")

        else:
            print(f"❌ Training failed: {result.get('error')}")
    else:
        print(f"❌ API request failed: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
