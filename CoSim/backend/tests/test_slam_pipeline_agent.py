"""Tests for the SLAM Pipeline Agent service layer and API.

TDD: These tests define the expected behaviour of the SLAM pipeline agent
before the implementation exists.
"""
from __future__ import annotations

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
async def test_slam_config_schema():
    """SLAMConfig validates required fields for SLAM pipeline."""
    from co_sim.services.slam_pipeline_agent import SLAMConfig

    config = SLAMConfig(
        workspace_id="ws-1",
        algorithm="ORB-SLAM2",
        dataset_path="/datasets/TUM-RGBD/fr1_xyz",
        dataset_type="TUM-RGBD",
        config_file="config/tum_rgbd.yaml",
    )
    assert config.algorithm in ("ORB-SLAM2", "ORB-SLAM3", "RTAB-Map", "LSD-SLAM")
    assert config.dataset_type in ("TUM-RGBD", "KITTI", "EuRoC", "Custom")


@pytest.mark.asyncio
async def test_trajectory_result_schema():
    """TrajectoryResult captures estimated camera trajectory."""
    from co_sim.services.slam_pipeline_agent import TrajectoryResult

    result = TrajectoryResult(
        run_id="slam-run-1",
        timestamps=[1.0, 2.0, 3.0],
        positions=[[0, 0, 0], [0.1, 0, 0], [0.2, 0, 0]],
        orientations=[[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],  # quaternions
    )
    assert len(result.timestamps) == len(result.positions)
    assert len(result.positions) == len(result.orientations)


@pytest.mark.asyncio
async def test_slam_metrics_schema():
    """SLAMMetrics captures ATE, RPE, and tracking quality."""
    from co_sim.services.slam_pipeline_agent import SLAMMetrics

    metrics = SLAMMetrics(
        run_id="slam-run-1",
        ate_rmse=0.05,  # Absolute Trajectory Error
        rpe_rmse=0.02,  # Relative Pose Error
        tracking_ratio=0.95,  # % of frames successfully tracked
        num_keyframes=150,
    )
    assert metrics.ate_rmse >= 0
    assert metrics.rpe_rmse >= 0
    assert 0 <= metrics.tracking_ratio <= 1


# ---------------------------------------------------------------------------
# Dataset mounting tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mount_dataset(tmp_path):
    """Mount a SLAM dataset from workspace storage."""
    from co_sim.services.slam_pipeline_agent import mount_dataset

    # Create mock dataset structure
    dataset_dir = tmp_path / "tum_dataset"
    dataset_dir.mkdir()
    (dataset_dir / "rgb.txt").write_text("# timestamp filename\n1.0 rgb/1.png\n")
    (dataset_dir / "groundtruth.txt").write_text("# timestamp tx ty tz qx qy qz qw\n1.0 0 0 0 0 0 0 1\n")

    result = await mount_dataset(
        dataset_path=str(dataset_dir),
        dataset_type="TUM-RGBD",
    )

    assert result["status"] == "mounted"
    assert result["num_frames"] > 0
    assert "rgb.txt" in result["files"]


@pytest.mark.asyncio
async def test_load_ground_truth(tmp_path):
    """Load ground truth trajectory from dataset."""
    from co_sim.services.slam_pipeline_agent import load_ground_truth

    # Create mock ground truth file
    gt_file = tmp_path / "groundtruth.txt"
    gt_content = """# timestamp tx ty tz qx qy qz qw
1.0 0.0 0.0 0.0 0 0 0 1
2.0 0.1 0.0 0.0 0 0 0 1
3.0 0.2 0.0 0.0 0 0 0 1
"""
    gt_file.write_text(gt_content)

    trajectory = await load_ground_truth(str(gt_file), format="TUM-RGBD")

    assert len(trajectory.timestamps) == 3
    assert trajectory.timestamps[0] == 1.0
    assert trajectory.positions[1] == [0.1, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Trajectory alignment tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_align_trajectories():
    """Align estimated trajectory to ground truth using Umeyama alignment."""
    from co_sim.services.slam_pipeline_agent import align_trajectories, TrajectoryResult

    # Ground truth trajectory (straight line along x-axis)
    gt = TrajectoryResult(
        run_id="gt",
        timestamps=[1.0, 2.0, 3.0],
        positions=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
        orientations=[[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
    )

    # Estimated trajectory (slightly scaled and rotated)
    estimated = TrajectoryResult(
        run_id="est",
        timestamps=[1.0, 2.0, 3.0],
        positions=[[0, 0, 0], [0.9, 0.1, 0], [1.8, 0.2, 0]],
        orientations=[[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
    )

    aligned = await align_trajectories(estimated, gt)

    # Aligned trajectory should be closer to ground truth
    assert len(aligned.positions) == len(gt.positions)
    # After alignment, positions should be closer to GT
    for aligned_pos, gt_pos in zip(aligned.positions, gt.positions):
        distance = np.linalg.norm(np.array(aligned_pos) - np.array(gt_pos))
        assert distance < 0.5  # Should be reasonably close after alignment


# ---------------------------------------------------------------------------
# Trajectory error metrics (ATE/RPE) tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compute_ate():
    """Compute Absolute Trajectory Error (ATE) RMSE."""
    from co_sim.services.slam_pipeline_agent import compute_ate, TrajectoryResult

    gt = TrajectoryResult(
        run_id="gt",
        timestamps=[1.0, 2.0, 3.0],
        positions=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
        orientations=[[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
    )

    estimated = TrajectoryResult(
        run_id="est",
        timestamps=[1.0, 2.0, 3.0],
        positions=[[0, 0, 0], [1.1, 0, 0], [2.2, 0, 0]],  # Small errors
        orientations=[[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
    )

    ate_rmse = await compute_ate(estimated, gt)

    assert ate_rmse > 0  # Should have some error
    assert ate_rmse < 0.3  # But not too large for this example


@pytest.mark.asyncio
async def test_compute_rpe():
    """Compute Relative Pose Error (RPE) RMSE."""
    from co_sim.services.slam_pipeline_agent import compute_rpe, TrajectoryResult

    gt = TrajectoryResult(
        run_id="gt",
        timestamps=[1.0, 2.0, 3.0, 4.0],
        positions=[[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]],
        orientations=[[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
    )

    estimated = TrajectoryResult(
        run_id="est",
        timestamps=[1.0, 2.0, 3.0, 4.0],
        positions=[[0, 0, 0], [0.95, 0, 0], [1.9, 0, 0], [2.85, 0, 0]],
        orientations=[[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
    )

    rpe_rmse = await compute_rpe(estimated, gt, delta=1)

    assert rpe_rmse > 0
    assert rpe_rmse < 0.2  # Should be small for this example


# ---------------------------------------------------------------------------
# SLAM pipeline execution tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_slam_pipeline(tmp_path):
    """Run complete SLAM pipeline on a dataset."""
    from co_sim.services.slam_pipeline_agent import run_slam_pipeline, SLAMConfig

    # Create mock dataset
    dataset_dir = tmp_path / "test_dataset"
    dataset_dir.mkdir()
    (dataset_dir / "rgb.txt").write_text("# timestamp filename\n1.0 rgb/1.png\n")
    (dataset_dir / "groundtruth.txt").write_text("# timestamp tx ty tz qx qy qz qw\n1.0 0 0 0 0 0 0 1\n")

    config = SLAMConfig(
        workspace_id="ws-slam",
        algorithm="ORB-SLAM2",
        dataset_path=str(dataset_dir),
        dataset_type="TUM-RGBD",
        config_file="config/test.yaml",
    )

    result = await run_slam_pipeline(config)

    assert result["status"] == "completed"
    assert "trajectory" in result
    assert "metrics" in result


# ---------------------------------------------------------------------------
# State persistence in Redis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_slam_metrics():
    """SLAM metrics are persisted to Redis for monitoring."""
    from co_sim.services.slam_pipeline_agent import persist_slam_metrics, get_slam_metrics

    await persist_slam_metrics(
        run_id="slam-1",
        ate_rmse=0.05,
        rpe_rmse=0.02,
        tracking_ratio=0.95,
        num_keyframes=150,
    )

    metrics = await get_slam_metrics("slam-1")
    assert metrics is not None
    assert metrics["ate_rmse"] == 0.05
    assert metrics["rpe_rmse"] == 0.02
    assert metrics["tracking_ratio"] == 0.95


@pytest.mark.asyncio
async def test_persist_slam_trajectory():
    """SLAM trajectory is persisted to Redis."""
    from co_sim.services.slam_pipeline_agent import (
        persist_slam_trajectory,
        get_slam_trajectory,
        TrajectoryResult,
    )

    trajectory = TrajectoryResult(
        run_id="slam-2",
        timestamps=[1.0, 2.0, 3.0],
        positions=[[0, 0, 0], [0.1, 0, 0], [0.2, 0, 0]],
        orientations=[[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]],
    )

    await persist_slam_trajectory(trajectory)

    loaded = await get_slam_trajectory("slam-2")
    assert loaded is not None
    assert loaded.run_id == "slam-2"
    assert len(loaded.timestamps) == 3


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slam_pipeline_end_to_end(tmp_path):
    """Complete SLAM pipeline: mount dataset, run SLAM, compute metrics, persist results."""
    from co_sim.services.slam_pipeline_agent import (
        SLAMConfig,
        mount_dataset,
        run_slam_pipeline,
        persist_slam_metrics,
        get_slam_metrics,
    )

    # Setup mock dataset
    dataset_dir = tmp_path / "e2e_dataset"
    dataset_dir.mkdir()
    (dataset_dir / "rgb.txt").write_text("# timestamp filename\n1.0 rgb/1.png\n2.0 rgb/2.png\n")
    (dataset_dir / "groundtruth.txt").write_text(
        "# timestamp tx ty tz qx qy qz qw\n1.0 0 0 0 0 0 0 1\n2.0 0.1 0 0 0 0 0 1\n"
    )

    # Mount dataset
    mount_result = await mount_dataset(str(dataset_dir), "TUM-RGBD")
    assert mount_result["status"] == "mounted"

    # Run SLAM pipeline
    config = SLAMConfig(
        workspace_id="ws-e2e",
        algorithm="ORB-SLAM2",
        dataset_path=str(dataset_dir),
        dataset_type="TUM-RGBD",
        config_file="config/test.yaml",
    )

    pipeline_result = await run_slam_pipeline(config)
    assert pipeline_result["status"] == "completed"

    # Verify metrics were persisted
    metrics = await get_slam_metrics(pipeline_result["run_id"])
    assert metrics is not None
    assert "ate_rmse" in metrics
    assert "rpe_rmse" in metrics
