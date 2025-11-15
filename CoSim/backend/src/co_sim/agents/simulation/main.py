"""Simulation Agent - Main FastAPI application for MuJoCo/PyBullet simulation."""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from co_sim.agents.simulation.mujoco_env import MuJoCoStreamManager, MUJOCO_AVAILABLE
from co_sim.agents.simulation.pybullet_env import PyBulletStreamManager, PYBULLET_AVAILABLE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global simulation managers
simulations: Dict[str, any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the application."""
    logger.info("Simulation Agent starting up...")
    logger.info(f"MuJoCo available: {MUJOCO_AVAILABLE}")
    logger.info(f"PyBullet available: {PYBULLET_AVAILABLE}")
    yield
    # Cleanup
    logger.info("Simulation Agent shutting down...")
    for session_id, sim in simulations.items():
        try:
            sim.close()
        except Exception as e:
            logger.error(f"Error closing simulation {session_id}: {e}")


app = FastAPI(
    title="CoSim Simulation Agent",
    description="MuJoCo and PyBullet simulation orchestration with WebRTC streaming",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response Models ---

class CreateSimulationRequest(BaseModel):
    """Request to create a new simulation instance."""
    session_id: str
    engine: str  # 'mujoco' or 'pybullet'
    model_path: Optional[str] = None
    width: int = 640
    height: int = 480
    fps: int = 60
    headless: bool = True


class SimulationControlRequest(BaseModel):
    """Request to control simulation (play, pause, reset, step)."""
    action: str  # 'play', 'pause', 'reset', 'step'
    actions: Optional[list] = None  # Control actions for step


class CameraControlRequest(BaseModel):
    """Request to update camera position."""
    distance: float = 2.5
    yaw: float = 50.0
    pitch: float = -35.0
    target: list = [0, 0, 0]


# --- Health Check ---

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "mujoco_available": MUJOCO_AVAILABLE,
        "pybullet_available": PYBULLET_AVAILABLE,
        "active_simulations": len(simulations),
    }


# --- Simulation Management ---

@app.post("/simulations/create")
async def create_simulation(request: CreateSimulationRequest):
    """Create a new simulation instance.
    
    Args:
        request: Simulation configuration
    
    Returns:
        Simulation creation status and metadata
    """
    session_id = request.session_id
    
    if session_id in simulations:
        raise HTTPException(status_code=400, detail=f"Simulation {session_id} already exists")
    
    try:
        if request.engine == "mujoco":
            if not MUJOCO_AVAILABLE:
                raise HTTPException(status_code=503, detail="MuJoCo is not available")
            if not request.model_path:
                raise HTTPException(status_code=400, detail="model_path required for MuJoCo")
            
            sim = MuJoCoStreamManager(
                model_path=request.model_path,
                width=request.width,
                height=request.height,
                fps=request.fps,
                headless=request.headless,
            )
            
        elif request.engine == "pybullet":
            if not PYBULLET_AVAILABLE:
                raise HTTPException(status_code=503, detail="PyBullet is not available")
            
            sim = PyBulletStreamManager(
                urdf_path=request.model_path,
                width=request.width,
                height=request.height,
                fps=request.fps,
                headless=request.headless,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown engine: {request.engine}")
        
        simulations[session_id] = sim
        
        logger.info(f"Created {request.engine} simulation for session {session_id}")
        
        return {
            "status": "created",
            "session_id": session_id,
            "engine": request.engine,
            "state": sim.get_state(),
        }
    
    except Exception as e:
        logger.error(f"Failed to create simulation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/simulations/{session_id}/state")
async def get_simulation_state(session_id: str):
    """Get current simulation state.
    
    Args:
        session_id: Session identifier
    
    Returns:
        Current simulation state
    """
    if session_id not in simulations:
        raise HTTPException(status_code=404, detail=f"Simulation {session_id} not found")
    
    sim = simulations[session_id]
    return sim.get_state()


@app.post("/simulations/{session_id}/control")
async def control_simulation(session_id: str, request: SimulationControlRequest):
    """Control simulation (play, pause, reset, step).
    
    Args:
        session_id: Session identifier
        request: Control action and parameters
    
    Returns:
        Updated simulation state
    """
    if session_id not in simulations:
        raise HTTPException(status_code=404, detail=f"Simulation {session_id} not found")
    
    sim = simulations[session_id]
    
    try:
        if request.action == "reset":
            result = sim.reset()
        elif request.action == "step":
            import numpy as np
            actions = np.array(request.actions) if request.actions else None
            result = sim.step(actions)
        elif request.action == "play":
            result = {"status": "playing", "message": "Use WebSocket for continuous streaming"}
        elif request.action == "pause":
            await sim.stop_streaming()
            result = {"status": "paused"}
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")
        
        return result
    
    except Exception as e:
        logger.error(f"Control error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/simulations/{session_id}/camera")
async def set_camera(session_id: str, request: CameraControlRequest):
    """Update camera position (PyBullet only).
    
    Args:
        session_id: Session identifier
        request: Camera parameters
    
    Returns:
        Confirmation
    """
    if session_id not in simulations:
        raise HTTPException(status_code=404, detail=f"Simulation {session_id} not found")
    
    sim = simulations[session_id]
    
    if hasattr(sim, 'set_camera'):
        sim.set_camera(
            distance=request.distance,
            yaw=request.yaw,
            pitch=request.pitch,
            target=request.target,
        )
        return {"status": "camera_updated"}
    else:
        return {"status": "not_supported", "message": "Camera control not supported for this engine"}


@app.delete("/simulations/{session_id}")
async def delete_simulation(session_id: str):
    """Delete simulation instance.
    
    Args:
        session_id: Session identifier
    
    Returns:
        Deletion confirmation
    """
    if session_id not in simulations:
        raise HTTPException(status_code=404, detail=f"Simulation {session_id} not found")
    
    sim = simulations[session_id]
    await sim.stop_streaming()
    sim.close()
    del simulations[session_id]
    
    logger.info(f"Deleted simulation {session_id}")
    
    return {"status": "deleted", "session_id": session_id}


# --- WebSocket Streaming ---

@app.websocket("/simulations/{session_id}/stream")
async def stream_simulation(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming simulation frames.
    
    Args:
        websocket: WebSocket connection
        session_id: Session identifier
    """
    if session_id not in simulations:
        await websocket.close(code=1008, reason=f"Simulation {session_id} not found")
        return
    
    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")
    
    sim = simulations[session_id]
    
    async def send_frame(frame_bytes: bytes):
        """Send frame to client."""
        try:
            await websocket.send_bytes(frame_bytes)
        except Exception as e:
            logger.error(f"Failed to send frame: {e}")
    
    try:
        # Start streaming
        await sim.start_streaming(send_frame)
        
        # Keep connection alive and handle control messages
        while True:
            message = await websocket.receive_text()
            
            # Handle control commands via WebSocket
            if message == "pause":
                await sim.stop_streaming()
            elif message == "play":
                if not sim.is_streaming:
                    await sim.start_streaming(send_frame)
            elif message == "reset":
                await sim.stop_streaming()
                sim.reset()
            elif message == "ping":
                await websocket.send_text("pong")
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        await sim.stop_streaming()


# --- Info Endpoints ---

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "CoSim Simulation Agent",
        "version": "1.0.0",
        "engines": {
            "mujoco": MUJOCO_AVAILABLE,
            "pybullet": PYBULLET_AVAILABLE,
        },
    }


# --- Code Execution ---

class ExecuteCodeRequest(BaseModel):
    """Request to execute Python code in simulation context."""
    code: str
    model_path: Optional[str] = None  # Optional MuJoCo/PyBullet model file
    working_dir: Optional[str] = None  # Optional working directory


@app.post("/simulations/{session_id}/execute")
async def execute_code(session_id: str, request: ExecuteCodeRequest):
    """Execute Python code with access to simulation API.
    
    This allows users to write control scripts that interact with the simulation:
    - sim.reset() - Reset simulation
    - sim.step(actions) - Step with actions
    - sim.get_state() - Get current state
    - sim.render() - Get rendered frame
    
    Args:
        session_id: Session identifier
        request: Code to execute and optional model path
    
    Returns:
        Execution results including stdout, stderr, and final state
    """
    import sys
    import os
    from io import StringIO
    
    if session_id not in simulations:
        raise HTTPException(status_code=404, detail=f"Simulation {session_id} not found")
    
    sim = simulations[session_id]
    
    # Capture stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    
    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        
        # Create execution context with simulation API
        context = {
            'sim': sim,
            'np': __import__('numpy'),
            'time': __import__('time'),
            'get_simulation': lambda: sim,  # Alias for CoSim compatibility
        }
        
        # Change working directory if specified
        if request.working_dir and os.path.exists(request.working_dir):
            os.chdir(request.working_dir)
        
        # Execute user code
        exec(request.code, context)
        
        # Get final simulation state (with error handling)
        try:
            final_state = sim.get_state()
        except Exception as e:
            logger.warning(f"Could not get final state: {e}")
            final_state = {"status": "completed", "note": "State unavailable after execution"}
        
        return {
            "status": "success",
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
            "state": final_state,
            "simulation_active": session_id in simulations,
        }
    
    except Exception as e:
        logger.error(f"Code execution error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
        }
    
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")
