"""ORB-SLAM2 Pipeline Template

This template demonstrates how to run ORB-SLAM2 on a TUM RGB-D dataset
using the CoSim SLAM pipeline infrastructure.

Usage:
    python run_slam.py --dataset /path/to/TUM/dataset
"""
import argparse
import asyncio
import requests
import json


async def main():
    """Run ORB-SLAM2 on TUM RGB-D dataset."""

    parser = argparse.ArgumentParser(description="Run ORB-SLAM2 on TUM RGB-D dataset")
    parser.add_argument(
        "--dataset",
        type=str,
        default="/datasets/TUM-RGBD/rgbd_dataset_freiburg1_xyz",
        help="Path to TUM RGB-D dataset"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/TUM1.yaml",
        help="Path to ORB-SLAM2 config file"
    )
    args = parser.parse_args()

    # Configure SLAM run
    config = {
        "workspace_id": "slam-demo",
        "algorithm": "ORB-SLAM2",
        "dataset_path": args.dataset,
        "dataset_type": "TUM-RGBD",
        "config_file": args.config,
    }

    print("=" * 60)
    print("ORB-SLAM2 Pipeline")
    print("=" * 60)
    print(f"Algorithm: {config['algorithm']}")
    print(f"Dataset: {config['dataset_path']}")
    print(f"Dataset Type: {config['dataset_type']}")
    print(f"Config: {config['config_file']}")
    print()

    # Step 1: Mount dataset
    print("Step 1: Mounting dataset...")
    mount_response = requests.post(
        "http://localhost:8000/slam/datasets/mount",
        json={
            "dataset_path": config["dataset_path"],
            "dataset_type": config["dataset_type"]
        }
    )

    if mount_response.status_code == 200:
        mount_result = mount_response.json()
        print(f"✅ Dataset mounted successfully")
        print(f"   Frames: {mount_result['num_frames']}")
        print(f"   Files: {', '.join(mount_result['files'][:5])}...")
        print()
    else:
        print(f"❌ Failed to mount dataset: {mount_response.status_code}")
        print(mount_response.text)
        return

    # Step 2: Run SLAM pipeline
    print("Step 2: Running SLAM pipeline...")
    slam_response = requests.post(
        "http://localhost:8000/slam/run",
        json=config
    )

    if slam_response.status_code == 200:
        result = slam_response.json()

        if result["status"] == "completed":
            run_id = result["run_id"]
            print(f"✅ SLAM pipeline completed successfully!")
            print(f"Run ID: {run_id}")
            print()

            # Display metrics
            if result["metrics"]:
                metrics = result["metrics"]
                print("Evaluation Metrics:")
                print(f"  ATE RMSE: {metrics['ate_rmse']:.4f} m")
                print(f"  RPE RMSE: {metrics['rpe_rmse']:.4f} m")
                print(f"  Tracking Ratio: {metrics['tracking_ratio']:.2%}")
                print(f"  Keyframes: {metrics['num_keyframes']}")
                print()

            # Display trajectory info
            if result["trajectory"]:
                traj = result["trajectory"]
                print(f"Trajectory: {len(traj['timestamps'])} poses")
                print(f"  Start: [{traj['positions'][0][0]:.2f}, {traj['positions'][0][1]:.2f}, {traj['positions'][0][2]:.2f}]")
                print(f"  End: [{traj['positions'][-1][0]:.2f}, {traj['positions'][-1][1]:.2f}, {traj['positions'][-1][2]:.2f}]")
                print()

            # Show API endpoints
            print("View results:")
            print(f"  Metrics: curl http://localhost:8000/slam/runs/{run_id}/metrics")
            print(f"  Trajectory: curl http://localhost:8000/slam/runs/{run_id}/trajectory")

        else:
            print(f"❌ SLAM failed: {result.get('error')}")
    else:
        print(f"❌ API request failed: {slam_response.status_code}")
        print(slam_response.text)


if __name__ == "__main__":
    asyncio.run(main())
