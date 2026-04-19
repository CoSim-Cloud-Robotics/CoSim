"""PyBullet PPO Training Template

This template demonstrates how to train a PPO agent on a PyBullet environment
using the CoSim RL training infrastructure.

Usage:
    python train_ppo.py
"""
import asyncio
import requests


async def main():
    """Train PPO agent on CartPole with PyBullet."""

    # Configure training run
    config = {
        "workspace_id": "pybullet-ppo-demo",
        "algorithm": "PPO",
        "environment": "CartPole-v1",
        "total_timesteps": 50000,
        "n_envs": 4,  # Parallel environments
        "learning_rate": 0.0003,
        "batch_size": 64,
        "gamma": 0.99,
    }

    print("Starting PPO training on CartPole...")
    print(f"Algorithm: {config['algorithm']}")
    print(f"Environment: {config['environment']}")
    print(f"Total timesteps: {config['total_timesteps']}")
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

            # Monitor training progress
            print("You can monitor progress with:")
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
