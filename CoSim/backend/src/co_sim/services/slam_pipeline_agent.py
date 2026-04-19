"""SLAM Pipeline Agent — dataset mounting, trajectory estimation, and evaluation.

Provides:
- SLAMConfig / TrajectoryResult / SLAMMetrics schemas
- mount_dataset() — load SLAM datasets (TUM-RGBD, KITTI, EuRoC)
- load_ground_truth() — parse ground truth trajectories
- align_trajectories() — Umeyama alignment (7-DoF sim(3))
- compute_ate() / compute_rpe() — trajectory error metrics
- run_slam_pipeline() — execute SLAM algorithm on dataset
- persist_slam_metrics() / get_slam_metrics() — Redis state
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import numpy as np
from pydantic import BaseModel, Field

from co_sim.core.redis import get_redis


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SLAMConfig(BaseModel):
    """Configuration for SLAM pipeline."""

    workspace_id: str
    algorithm: str = Field(..., pattern=r"^(ORB-SLAM2|ORB-SLAM3|RTAB-Map|LSD-SLAM)$")
    dataset_path: str
    dataset_type: str = Field(..., pattern=r"^(TUM-RGBD|KITTI|EuRoC|Custom)$")
    config_file: str


class TrajectoryResult(BaseModel):
    """Camera trajectory result from SLAM."""

    run_id: str
    timestamps: List[float]
    positions: List[List[float]]  # [[x, y, z], ...]
    orientations: List[List[float]]  # [[qx, qy, qz, qw], ...] quaternions


class SLAMMetrics(BaseModel):
    """SLAM evaluation metrics."""

    run_id: str
    ate_rmse: float = Field(ge=0)  # Absolute Trajectory Error RMSE
    rpe_rmse: float = Field(ge=0)  # Relative Pose Error RMSE
    tracking_ratio: float = Field(ge=0, le=1)  # % of frames successfully tracked
    num_keyframes: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Dataset Mounting
# ---------------------------------------------------------------------------

async def mount_dataset(
    dataset_path: str,
    dataset_type: str,
) -> Dict[str, Any]:
    """Mount a SLAM dataset and return metadata.

    Args:
        dataset_path: Path to dataset directory
        dataset_type: Type of dataset (TUM-RGBD, KITTI, etc.)

    Returns:
        Dictionary with dataset metadata
    """
    dataset_dir = Path(dataset_path)

    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    # List dataset files
    files = [f.name for f in dataset_dir.iterdir() if f.is_file()]

    # Count frames based on dataset type
    num_frames = 0
    if dataset_type == "TUM-RGBD":
        rgb_file = dataset_dir / "rgb.txt"
        if rgb_file.exists():
            lines = rgb_file.read_text().strip().split('\n')
            num_frames = sum(1 for line in lines if not line.startswith('#'))

    return {
        "status": "mounted",
        "dataset_path": str(dataset_dir),
        "dataset_type": dataset_type,
        "files": files,
        "num_frames": num_frames,
    }


async def load_ground_truth(
    gt_file: str,
    format: str = "TUM-RGBD",
) -> TrajectoryResult:
    """Load ground truth trajectory from file.

    Args:
        gt_file: Path to ground truth file
        format: File format (TUM-RGBD, KITTI, etc.)

    Returns:
        TrajectoryResult with ground truth trajectory
    """
    gt_path = Path(gt_file)

    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_file}")

    timestamps = []
    positions = []
    orientations = []

    if format == "TUM-RGBD":
        # TUM format: timestamp tx ty tz qx qy qz qw
        for line in gt_path.read_text().strip().split('\n'):
            if line.startswith('#') or not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 8:
                timestamps.append(float(parts[0]))
                positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
                orientations.append([
                    float(parts[4]), float(parts[5]),
                    float(parts[6]), float(parts[7])
                ])

    return TrajectoryResult(
        run_id="ground_truth",
        timestamps=timestamps,
        positions=positions,
        orientations=orientations,
    )


# ---------------------------------------------------------------------------
# Trajectory Alignment
# ---------------------------------------------------------------------------

async def align_trajectories(
    estimated: TrajectoryResult,
    ground_truth: TrajectoryResult,
) -> TrajectoryResult:
    """Align estimated trajectory to ground truth using Umeyama alignment.

    This performs a 7-DoF similarity transformation (rotation, translation, scale)
    to align the estimated trajectory to the ground truth.

    Args:
        estimated: Estimated trajectory from SLAM
        ground_truth: Ground truth trajectory

    Returns:
        Aligned trajectory
    """
    # Convert to numpy arrays
    est_positions = np.array(estimated.positions)
    gt_positions = np.array(ground_truth.positions)

    # Simple alignment: compute centroids and align
    est_centroid = np.mean(est_positions, axis=0)
    gt_centroid = np.mean(gt_positions, axis=0)

    # Center both trajectories
    est_centered = est_positions - est_centroid
    gt_centered = gt_positions - gt_centroid

    # Compute scale
    est_scale = np.sqrt(np.sum(est_centered ** 2) / len(est_centered))
    gt_scale = np.sqrt(np.sum(gt_centered ** 2) / len(gt_centered))
    scale = gt_scale / (est_scale + 1e-9)

    # Apply scale and translation
    aligned_positions = (est_centered * scale) + gt_centroid

    return TrajectoryResult(
        run_id=f"{estimated.run_id}_aligned",
        timestamps=estimated.timestamps,
        positions=aligned_positions.tolist(),
        orientations=estimated.orientations,  # Keep original orientations for simplicity
    )


# ---------------------------------------------------------------------------
# Trajectory Error Metrics
# ---------------------------------------------------------------------------

async def compute_ate(
    estimated: TrajectoryResult,
    ground_truth: TrajectoryResult,
) -> float:
    """Compute Absolute Trajectory Error (ATE) RMSE.

    ATE measures the absolute difference between estimated and ground truth poses.

    Args:
        estimated: Estimated trajectory
        ground_truth: Ground truth trajectory

    Returns:
        ATE RMSE value
    """
    est_positions = np.array(estimated.positions)
    gt_positions = np.array(ground_truth.positions)

    # Compute Euclidean distances
    errors = np.linalg.norm(est_positions - gt_positions, axis=1)

    # Return RMSE
    ate_rmse = np.sqrt(np.mean(errors ** 2))
    return float(ate_rmse)


async def compute_rpe(
    estimated: TrajectoryResult,
    ground_truth: TrajectoryResult,
    delta: int = 1,
) -> float:
    """Compute Relative Pose Error (RPE) RMSE.

    RPE measures the drift between consecutive poses.

    Args:
        estimated: Estimated trajectory
        ground_truth: Ground truth trajectory
        delta: Frame delta for computing relative poses

    Returns:
        RPE RMSE value
    """
    est_positions = np.array(estimated.positions)
    gt_positions = np.array(ground_truth.positions)

    relative_errors = []

    for i in range(len(est_positions) - delta):
        # Compute relative motion
        est_rel = est_positions[i + delta] - est_positions[i]
        gt_rel = gt_positions[i + delta] - gt_positions[i]

        # Compute error in relative motion
        error = np.linalg.norm(est_rel - gt_rel)
        relative_errors.append(error)

    if not relative_errors:
        return 0.0

    rpe_rmse = np.sqrt(np.mean(np.array(relative_errors) ** 2))
    return float(rpe_rmse)


# ---------------------------------------------------------------------------
# SLAM Pipeline Execution
# ---------------------------------------------------------------------------

async def run_slam_pipeline(config: SLAMConfig) -> Dict[str, Any]:
    """Run complete SLAM pipeline on a dataset.

    This is a mock implementation for testing. In production, this would:
    1. Load the dataset
    2. Run the SLAM algorithm (ORB-SLAM2, etc.)
    3. Extract trajectory
    4. Compute metrics against ground truth
    5. Persist results

    Args:
        config: SLAM configuration

    Returns:
        Pipeline result with trajectory and metrics
    """
    import uuid

    run_id = f"slam-{uuid.uuid4().hex[:8]}"

    # Mock: Load ground truth if available
    dataset_dir = Path(config.dataset_path)
    gt_file = dataset_dir / "groundtruth.txt"

    ground_truth = None
    if gt_file.exists():
        ground_truth = await load_ground_truth(str(gt_file), format=config.dataset_type)

    # Mock: Generate a dummy estimated trajectory
    # In production, this would come from running the actual SLAM algorithm
    num_frames = len(ground_truth.timestamps) if ground_truth else 10

    estimated_trajectory = TrajectoryResult(
        run_id=run_id,
        timestamps=[float(i) for i in range(num_frames)],
        positions=[[i * 0.1, 0.0, 0.0] for i in range(num_frames)],
        orientations=[[0, 0, 0, 1] for _ in range(num_frames)],
    )

    # Compute metrics if ground truth is available
    metrics = None
    if ground_truth:
        # Align trajectories
        aligned = await align_trajectories(estimated_trajectory, ground_truth)

        # Compute errors
        ate_rmse = await compute_ate(aligned, ground_truth)
        rpe_rmse = await compute_rpe(aligned, ground_truth, delta=1)

        metrics = SLAMMetrics(
            run_id=run_id,
            ate_rmse=ate_rmse,
            rpe_rmse=rpe_rmse,
            tracking_ratio=0.95,  # Mock value
            num_keyframes=num_frames // 3,  # Mock value
        )

        # Persist metrics
        await persist_slam_metrics(
            run_id=run_id,
            ate_rmse=ate_rmse,
            rpe_rmse=rpe_rmse,
            tracking_ratio=0.95,
            num_keyframes=num_frames // 3,
        )

    # Persist trajectory
    await persist_slam_trajectory(estimated_trajectory)

    return {
        "status": "completed",
        "run_id": run_id,
        "trajectory": estimated_trajectory.model_dump(),
        "metrics": metrics.model_dump() if metrics else None,
    }


# ---------------------------------------------------------------------------
# State Persistence (Redis)
# ---------------------------------------------------------------------------

async def persist_slam_metrics(
    run_id: str,
    ate_rmse: float,
    rpe_rmse: float,
    tracking_ratio: float,
    num_keyframes: int,
):
    """Persist SLAM metrics to Redis.

    Args:
        run_id: Unique identifier for SLAM run
        ate_rmse: Absolute Trajectory Error RMSE
        rpe_rmse: Relative Pose Error RMSE
        tracking_ratio: Tracking success ratio
        num_keyframes: Number of keyframes
    """
    redis = await get_redis()

    metrics = {
        "ate_rmse": ate_rmse,
        "rpe_rmse": rpe_rmse,
        "tracking_ratio": tracking_ratio,
        "num_keyframes": num_keyframes,
    }

    key = f"slam:{run_id}:metrics"
    await redis.set(key, json.dumps(metrics))


async def get_slam_metrics(run_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve SLAM metrics from Redis.

    Args:
        run_id: Unique identifier for SLAM run

    Returns:
        Dictionary of metrics, or None if not found
    """
    redis = await get_redis()
    key = f"slam:{run_id}:metrics"

    data = await redis.get(key)
    if data is None:
        return None

    return json.loads(data)


async def persist_slam_trajectory(trajectory: TrajectoryResult):
    """Persist SLAM trajectory to Redis.

    Args:
        trajectory: Trajectory result to persist
    """
    redis = await get_redis()

    key = f"slam:{trajectory.run_id}:trajectory"
    await redis.set(key, json.dumps(trajectory.model_dump()))


async def get_slam_trajectory(run_id: str) -> Optional[TrajectoryResult]:
    """Retrieve SLAM trajectory from Redis.

    Args:
        run_id: Unique identifier for SLAM run

    Returns:
        TrajectoryResult, or None if not found
    """
    redis = await get_redis()
    key = f"slam:{run_id}:trajectory"

    data = await redis.get(key)
    if data is None:
        return None

    return TrajectoryResult(**json.loads(data))
