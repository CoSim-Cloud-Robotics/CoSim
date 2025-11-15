"""PyBullet simulation environment wrapper with WebRTC streaming support."""
import asyncio
import base64
import io
import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image

try:
    import pybullet as p
    import pybullet_data
    PYBULLET_AVAILABLE = True
except ImportError:
    PYBULLET_AVAILABLE = False
    logging.warning("PyBullet not installed. Install with: pip install pybullet")

logger = logging.getLogger(__name__)


class PyBulletEnvironment:
    """PyBullet simulation environment with rendering and control."""
    
    def __init__(
        self,
        urdf_path: Optional[str] = None,
        width: int = 640,
        height: int = 480,
        fps: int = 60,
        headless: bool = True,
    ):
        """Initialize PyBullet environment.
        
        Args:
            urdf_path: Path to URDF model file (None for empty world)
            width: Render width in pixels
            height: Render height in pixels
            fps: Target frames per second
            headless: If True, use DIRECT mode; if False, use GUI mode
        """
        if not PYBULLET_AVAILABLE:
            raise RuntimeError("PyBullet is not installed. Please install: pip install pybullet")
        
        self.urdf_path = urdf_path
        self.width = width
        self.height = height
        self.fps = fps
        self.headless = headless
        
        # Connect to physics server
        if headless:
            self.physics_client = p.connect(p.DIRECT)
        else:
            self.physics_client = p.connect(p.GUI)
        
        # Set up data path
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        
        # Simulation state
        self.is_running = False
        self.frame_count = 0
        self.simulation_time = 0.0
        self.time_step = 1.0 / 240.0  # PyBullet default
        
        # Camera setup for rendering
        self.camera_distance = 2.5
        self.camera_yaw = 50
        self.camera_pitch = -35
        self.camera_target = [0, 0, 0]
        
        # Load environment
        self._setup_environment()
        
        logger.info(f"PyBullet environment initialized (headless={headless})")
        if urdf_path:
            logger.info(f"Loaded model: {urdf_path}")
    
    def _setup_environment(self):
        """Set up the simulation environment."""
        # Set gravity
        p.setGravity(0, 0, -9.81)
        
        # Set time step
        p.setTimeStep(self.time_step)
        
        # Load plane
        self.plane_id = p.loadURDF("plane.urdf")
        
        # Load model if provided
        self.robot_id = None
        if self.urdf_path:
            try:
                self.robot_id = p.loadURDF(
                    self.urdf_path,
                    basePosition=[0, 0, 1],
                    useFixedBase=False
                )
                logger.info(f"Loaded robot with ID: {self.robot_id}")
            except Exception as e:
                logger.error(f"Failed to load URDF {self.urdf_path}: {e}")
    
    def reset(self) -> Dict[str, Any]:
        """Reset simulation to initial state.
        
        Returns:
            Dictionary with reset confirmation and initial state
        """
        p.resetSimulation(self.physics_client)
        self._setup_environment()
        
        self.frame_count = 0
        self.simulation_time = 0.0
        
        logger.info("PyBullet simulation reset")
        return {
            "status": "reset",
            "frame": self.frame_count,
            "time": self.simulation_time,
            "num_bodies": p.getNumBodies(),
        }
    
    def step(self, actions: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """Step the simulation forward by one timestep.
        
        Args:
            actions: Optional control actions (joint torques/velocities)
        
        Returns:
            Dictionary with state information after step
        """
        # Apply actions if provided
        if actions is not None and self.robot_id is not None:
            num_joints = p.getNumJoints(self.robot_id)
            for i in range(min(len(actions), num_joints)):
                p.setJointMotorControl2(
                    self.robot_id,
                    i,
                    p.TORQUE_CONTROL,
                    force=actions[i]
                )
        
        # Step simulation
        p.stepSimulation()
        
        self.frame_count += 1
        self.simulation_time += self.time_step
        
        # Get robot state if available
        robot_state = {}
        if self.robot_id is not None:
            base_pos, base_orn = p.getBasePositionAndOrientation(self.robot_id)
            robot_state = {
                "base_position": list(base_pos),
                "base_orientation": list(base_orn),
            }
        
        return {
            "status": "stepped",
            "frame": self.frame_count,
            "time": self.simulation_time,
            **robot_state,
        }
    
    def render_frame(self) -> bytes:
        """Render current frame and return as JPEG bytes.
        
        Returns:
            JPEG-encoded image bytes
        """
        # Get camera view matrix
        view_matrix = p.computeViewMatrixFromYawPitchRoll(
            cameraTargetPosition=self.camera_target,
            distance=self.camera_distance,
            yaw=self.camera_yaw,
            pitch=self.camera_pitch,
            roll=0,
            upAxisIndex=2
        )
        
        # Get projection matrix
        proj_matrix = p.computeProjectionMatrixFOV(
            fov=60,
            aspect=self.width / self.height,
            nearVal=0.1,
            farVal=100.0
        )
        
        # Render image
        (_, _, px, _, _) = p.getCameraImage(
            width=self.width,
            height=self.height,
            viewMatrix=view_matrix,
            projectionMatrix=proj_matrix,
            renderer=p.ER_BULLET_HARDWARE_OPENGL if not self.headless else p.ER_TINY_RENDERER
        )
        
        # Convert to RGB and encode as JPEG
        rgb_array = np.array(px, dtype=np.uint8).reshape((self.height, self.width, 4))
        rgb_array = rgb_array[:, :, :3]  # Remove alpha channel
        
        image = Image.fromarray(rgb_array)
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()
    
    def get_frame_base64(self) -> str:
        """Render frame and encode as base64 string.
        
        Returns:
            Base64-encoded JPEG image
        """
        frame_bytes = self.render_frame()
        return base64.b64encode(frame_bytes).decode('utf-8')
    
    def get_state(self) -> Dict[str, Any]:
        """Get current simulation state.
        
        Returns:
            Dictionary with full state information
        """
        state = {
            "frame": self.frame_count,
            "time": self.simulation_time,
            "is_running": self.is_running,
        }
        
        # Try to get number of bodies, handle disconnected client
        try:
            state["num_bodies"] = p.getNumBodies()
        except Exception:
            state["num_bodies"] = 0
        
        # Add robot state if available
        if self.robot_id is not None:
            try:
                base_pos, base_orn = p.getBasePositionAndOrientation(self.robot_id)
                base_vel, base_ang_vel = p.getBaseVelocity(self.robot_id)
                
                state.update({
                    "robot_id": self.robot_id,
                    "base_position": list(base_pos),
                    "base_orientation": list(base_orn),
                    "base_velocity": list(base_vel),
                    "base_angular_velocity": list(base_ang_vel),
                })
            except Exception as e:
                # Robot may have been removed or client disconnected
                logger.warning(f"Could not get robot state: {e}")
                state["robot_id"] = None
        
        return state
    
    def set_camera(self, distance: float, yaw: float, pitch: float, target: list):
        """Update camera position.
        
        Args:
            distance: Camera distance from target
            yaw: Camera yaw angle (degrees)
            pitch: Camera pitch angle (degrees)
            target: [x, y, z] target position
        """
        self.camera_distance = distance
        self.camera_yaw = yaw
        self.camera_pitch = pitch
        self.camera_target = target
    
    def close(self):
        """Clean up resources."""
        p.disconnect(self.physics_client)
        logger.info("PyBullet environment closed")


class PyBulletStreamManager:
    """Manages PyBullet simulation lifecycle and frame streaming."""
    
    def __init__(self, urdf_path: Optional[str] = None, **kwargs):
        """Initialize stream manager.
        
        Args:
            urdf_path: Path to URDF model file
            **kwargs: Additional arguments for PyBulletEnvironment
        """
        self.env = PyBulletEnvironment(urdf_path, **kwargs)
        self.is_streaming = False
        self._stream_task: Optional[asyncio.Task] = None
    
    async def start_streaming(self, frame_callback):
        """Start streaming frames at target FPS.
        
        Args:
            frame_callback: Async function called with each frame (bytes)
        """
        if self.is_streaming:
            logger.warning("Streaming already active")
            return
        
        self.is_streaming = True
        self.env.is_running = True
        
        frame_interval = 1.0 / self.env.fps
        
        async def stream_loop():
            try:
                while self.is_streaming:
                    loop_start = asyncio.get_event_loop().time()
                    
                    # Step simulation
                    self.env.step()
                    
                    # Render and send frame
                    frame_bytes = self.env.render_frame()
                    if frame_bytes:
                        await frame_callback(frame_bytes)
                    
                    # Maintain target FPS
                    elapsed = asyncio.get_event_loop().time() - loop_start
                    sleep_time = max(0, frame_interval - elapsed)
                    await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                logger.info("Stream loop cancelled")
            except Exception as e:
                logger.error(f"Stream loop error: {e}", exc_info=True)
            finally:
                self.is_streaming = False
                self.env.is_running = False
        
        self._stream_task = asyncio.create_task(stream_loop())
        logger.info(f"Started streaming at {self.env.fps} FPS")
    
    async def stop_streaming(self):
        """Stop streaming frames."""
        if not self.is_streaming:
            return
        
        self.is_streaming = False
        self.env.is_running = False
        
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped streaming")
    
    def reset(self) -> Dict[str, Any]:
        """Reset simulation."""
        return self.env.reset()
    
    def step(self, actions: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """Step simulation."""
        return self.env.step(actions)
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state."""
        return self.env.get_state()
    
    def set_camera(self, **kwargs):
        """Set camera parameters."""
        self.env.set_camera(**kwargs)
    
    def close(self):
        """Close environment."""
        self.env.close()
