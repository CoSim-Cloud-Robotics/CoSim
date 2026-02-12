"""MuJoCo simulation environment wrapper with WebRTC streaming support."""
import asyncio
import base64
import io
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import numpy as np
from PIL import Image

try:
    import mujoco
    import mujoco.viewer
    MUJOCO_AVAILABLE = True
except ImportError:
    MUJOCO_AVAILABLE = False
    logging.warning("MuJoCo not installed. Install with: pip install mujoco")

logger = logging.getLogger(__name__)


class MuJoCoEnvironment:
    """MuJoCo simulation environment with rendering and control."""
    
    def __init__(
        self,
        model_path: str,
        width: int = 640,
        height: int = 480,
        fps: int = 60,
        headless: bool = True,
    ):
        """Initialize MuJoCo environment.
        
        Args:
            model_path: Path to MuJoCo XML model file
            width: Render width in pixels
            height: Render height in pixels
            fps: Target frames per second
            headless: If True, render offscreen; if False, open GUI viewer
        """
        if not MUJOCO_AVAILABLE:
            raise RuntimeError("MuJoCo is not installed. Please install: pip install mujoco")
        
        self.model_path = model_path
        self.width = width
        self.height = height
        self.fps = fps
        self.headless = headless
        
        # Load model and create data
        self.model = mujoco.MjModel.from_xml_path(model_path)
        self.data = mujoco.MjData(self.model)
        
        # Simulation state
        self.is_running = False
        self.frame_count = 0
        self.simulation_time = 0.0
        
        # Rendering setup
        if headless:
            self.renderer = mujoco.Renderer(self.model, height=height, width=width)
            self.viewer = None
        else:
            self.renderer = None
            self.viewer = mujoco.viewer.launch_passive(self.model, self.data)
        
        logger.info(f"MuJoCo environment initialized: {model_path}")
        logger.info(f"Model: {self.model.nq} DOFs, {self.model.nbody} bodies")
    
    def reset(self) -> Dict[str, Any]:
        """Reset simulation to initial state.
        
        Returns:
            Dictionary with reset confirmation and initial state
        """
        mujoco.mj_resetData(self.model, self.data)
        self.frame_count = 0
        self.simulation_time = 0.0
        
        logger.info("MuJoCo simulation reset")
        return {
            "status": "reset",
            "frame": self.frame_count,
            "time": self.simulation_time,
            "qpos": self.data.qpos.tolist(),
            "qvel": self.data.qvel.tolist(),
        }
    
    def step(self, actions: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """Step the simulation forward by one timestep.
        
        Args:
            actions: Optional control actions (numpy array matching model.nu)
        
        Returns:
            Dictionary with state information after step
        """
        # Apply actions if provided
        if actions is not None:
            if len(actions) != self.model.nu:
                raise ValueError(f"Actions must have length {self.model.nu}, got {len(actions)}")
            self.data.ctrl[:] = actions
        
        # Step simulation
        mujoco.mj_step(self.model, self.data)
        
        self.frame_count += 1
        self.simulation_time = self.data.time
        
        return {
            "status": "stepped",
            "frame": self.frame_count,
            "time": self.simulation_time,
            "qpos": self.data.qpos.tolist(),
            "qvel": self.data.qvel.tolist(),
        }
    
    def render_frame(self) -> bytes:
        """Render current frame and return as JPEG bytes.
        
        Returns:
            JPEG-encoded image bytes
        """
        if self.headless:
            # Update renderer and get pixels
            self.renderer.update_scene(self.data)
            pixels = self.renderer.render()
            
            # Convert to PIL Image and encode as JPEG
            image = Image.fromarray(pixels)
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            return buffer.getvalue()
        else:
            # For non-headless mode, viewer handles rendering
            if self.viewer:
                self.viewer.sync()
            return b''
    
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
        return {
            "frame": self.frame_count,
            "time": self.simulation_time,
            "is_running": self.is_running,
            "qpos": self.data.qpos.tolist(),
            "qvel": self.data.qvel.tolist(),
            "ctrl": self.data.ctrl.tolist(),
            "sensordata": self.data.sensordata.tolist() if self.model.nsensor > 0 else [],
        }
    
    def close(self):
        """Clean up resources."""
        if self.viewer:
            self.viewer.close()
        if self.renderer:
            self.renderer.close()
        logger.info("MuJoCo environment closed")


class MuJoCoStreamManager:
    """Manages MuJoCo simulation lifecycle and frame streaming."""
    
    def __init__(self, model_path: str, **kwargs):
        """Initialize stream manager.
        
        Args:
            model_path: Path to MuJoCo XML model
            **kwargs: Additional arguments for MuJoCoEnvironment
        """
        self.env = MuJoCoEnvironment(model_path, **kwargs)
        self.is_streaming = False
        self._stream_task: Optional[asyncio.Task] = None
    
    async def start_streaming(
        self,
        frame_callback,
        state_callback: Callable[[Dict[str, Any]], Awaitable[None] | None] | None = None,
    ):
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
        
        async def _maybe_emit_state(state: Dict[str, Any]):
            if not state_callback:
                return
            result = state_callback(state)
            if asyncio.iscoroutine(result):
                await result

        async def stream_loop():
            try:
                while self.is_streaming:
                    loop_start = asyncio.get_event_loop().time()
                    
                    # Step simulation
                    state = self.env.step()
                    
                    # Render and send frame
                    frame_bytes = self.env.render_frame()
                    if frame_bytes:
                        await frame_callback(frame_bytes)
                    await _maybe_emit_state(state)
                    
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
    
    def close(self):
        """Close environment."""
        self.env.close()
