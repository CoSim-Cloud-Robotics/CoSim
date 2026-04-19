# ORB-SLAM2 Template

This template provides a complete setup for running ORB-SLAM2 on standard SLAM datasets with automatic trajectory evaluation.

## Overview

- **Algorithm**: ORB-SLAM2 (monocular/stereo/RGB-D)
- **Datasets**: TUM RGB-D, KITTI, EuRoC
- **Framework**: CoSim SLAM Pipeline Agent
- **Features**:
  - Automatic dataset mounting
  - Ground truth trajectory alignment
  - ATE/RPE metrics computation
  - Trajectory visualization (coming soon)

## Quick Start

```bash
# Run on TUM RGB-D dataset
python run_slam.py --dataset /path/to/TUM/rgbd_dataset_freiburg1_xyz

# Run on KITTI dataset
python run_slam.py --dataset /path/to/KITTI/00 --config config/KITTI00.yaml
```

## Supported Datasets

### TUM RGB-D

Download from: https://vision.in.tum.de/data/datasets/rgbd-dataset

Sequences:
- `freiburg1_xyz` - Small loop closure
- `freiburg1_desk` - Office desk scene
- `freiburg2_xyz` - Large workspace
- `freiburg3_long_office_household` - Long office sequence

### KITTI Odometry

Download from: http://www.cvlibs.net/datasets/kitti/eval_odometry.php

Sequences:
- `00-10` - Various urban driving scenarios

### EuRoC MAV

Download from: https://projects.asl.ethz.ch/datasets/doku.php?id=kmavvisualinertialdatasets

Sequences:
- `MH_01_easy` - Machine hall (easy)
- `MH_02_easy` - Machine hall (easy)
- `V1_01_easy` - Vicon room (easy)

## Dataset Structure

### TUM RGB-D Format

```
rgbd_dataset_freiburg1_xyz/
├── rgb.txt              # RGB image timestamps and filenames
├── depth.txt            # Depth image timestamps and filenames
├── groundtruth.txt      # Ground truth trajectory
├── rgb/
│   ├── 1305031102.175304.png
│   └── ...
└── depth/
    ├── 1305031102.160407.png
    └── ...
```

## Evaluation Metrics

### Absolute Trajectory Error (ATE)

ATE measures the absolute difference between the estimated trajectory and ground truth:

```
ATE_RMSE = sqrt(1/N * sum(||p_est(i) - p_gt(i)||^2))
```

**Interpretation:**
- < 0.05m: Excellent
- 0.05-0.1m: Good
- 0.1-0.5m: Acceptable
- > 0.5m: Poor

### Relative Pose Error (RPE)

RPE measures the local drift between consecutive poses:

```
RPE_RMSE = sqrt(1/N * sum(||delta_est(i) - delta_gt(i)||^2))
```

**Interpretation:**
- < 0.01m: Excellent
- 0.01-0.05m: Good
- 0.05-0.1m: Acceptable
- > 0.1m: Poor

## Configuration

### ORB-SLAM2 Config Files

Located in `config/`:

**TUM1.yaml** - For TUM freiburg1 sequences:
```yaml
# Camera Parameters
Camera.fx: 517.3
Camera.fy: 516.5
Camera.cx: 318.6
Camera.cy: 255.3

# ORB Parameters
ORBextractor.nFeatures: 1000
ORBextractor.scaleFactor: 1.2
ORBextractor.nLevels: 8
```

**KITTI00.yaml** - For KITTI sequence 00:
```yaml
# Camera Parameters
Camera.fx: 718.856
Camera.fy: 718.856
Camera.cx: 607.1928
Camera.cy: 185.2157

# Stereo baseline
Camera.bf: 387.5744
```

## API Endpoints

### Mount Dataset

```bash
curl -X POST http://localhost:8000/slam/datasets/mount \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_path": "/datasets/TUM-RGBD/rgbd_dataset_freiburg1_xyz",
    "dataset_type": "TUM-RGBD"
  }'
```

### Run SLAM Pipeline

```bash
curl -X POST http://localhost:8000/slam/run \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "slam-test",
    "algorithm": "ORB-SLAM2",
    "dataset_path": "/datasets/TUM-RGBD/rgbd_dataset_freiburg1_xyz",
    "dataset_type": "TUM-RGBD",
    "config_file": "config/TUM1.yaml"
  }'
```

### Get Metrics

```bash
curl http://localhost:8000/slam/runs/{run_id}/metrics
```

Response:
```json
{
  "ate_rmse": 0.042,
  "rpe_rmse": 0.018,
  "tracking_ratio": 0.98,
  "num_keyframes": 142
}
```

### Get Trajectory

```bash
curl http://localhost:8000/slam/runs/{run_id}/trajectory
```

Response:
```json
{
  "run_id": "slam-abc123",
  "timestamps": [1.0, 2.0, 3.0, ...],
  "positions": [[0, 0, 0], [0.1, 0, 0], ...],
  "orientations": [[0, 0, 0, 1], ...]
}
```

## Visualization

### Plot Trajectory (Coming Soon)

```python
import matplotlib.pyplot as plt
import requests

# Get trajectory
response = requests.get(f"http://localhost:8000/slam/runs/{run_id}/trajectory")
traj = response.json()

# Plot
positions = traj["positions"]
xs = [p[0] for p in positions]
ys = [p[1] for p in positions]

plt.plot(xs, ys, 'b-', label='Estimated')
plt.plot(xs_gt, ys_gt, 'r--', label='Ground Truth')
plt.legend()
plt.show()
```

## Troubleshooting

### Low Tracking Ratio (< 0.8)

**Possible causes:**
- Poor lighting conditions
- Fast camera motion
- Texture-less scenes

**Solutions:**
- Adjust ORB feature parameters
- Reduce `ORBextractor.scaleFactor`
- Increase `ORBextractor.nFeatures`

### High ATE/RPE Errors

**Possible causes:**
- Scale drift (monocular only)
- Loop closure failures
- Incorrect camera calibration

**Solutions:**
- Verify camera parameters in config
- Enable loop closure detection
- Use stereo/RGB-D instead of monocular

## Benchmarks

### TUM RGB-D (freiburg1_xyz)

| Method | ATE RMSE | RPE RMSE | Tracking |
|--------|----------|----------|----------|
| ORB-SLAM2 RGB-D | 0.012m | 0.008m | 99.5% |
| ORB-SLAM3 RGB-D | 0.011m | 0.007m | 99.7% |

### KITTI Sequence 00

| Method | ATE RMSE | RPE RMSE |
|--------|----------|----------|
| ORB-SLAM2 Stereo | 5.2m | 0.8% |
| ORB-SLAM3 Stereo | 4.8m | 0.7% |

## Next Steps

1. **Custom datasets**: Add your own RGB-D sequences
2. **Algorithm comparison**: Compare ORB-SLAM2 vs ORB-SLAM3 vs RTAB-Map
3. **Real-time mode**: Run SLAM on live camera feed
4. **Map export**: Save reconstructed 3D maps

## References

- [ORB-SLAM2 Paper](https://arxiv.org/abs/1610.06475)
- [TUM RGB-D Dataset](https://vision.in.tum.de/data/datasets/rgbd-dataset)
- [KITTI Odometry Benchmark](http://www.cvlibs.net/datasets/kitti/eval_odometry.php)
