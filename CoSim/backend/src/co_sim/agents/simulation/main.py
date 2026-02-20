"""Simulation Agent - Main FastAPI application for MuJoCo/PyBullet simulation."""
import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from co_sim.agents.simulation.mujoco_env import MuJoCoStreamManager, MUJOCO_AVAILABLE
from co_sim.agents.simulation.pybullet_env import PyBulletStreamManager, PYBULLET_AVAILABLE
from co_sim.agents.simulation.session_tracker import get_active_sessions, handle_session_event
from co_sim.agents.simulation.webrtc import WebRTCBroadcaster
from co_sim.core.config import settings
from co_sim.core.redis import close_redis, init_redis
from co_sim.services import session_events, simulation_state


@dataclass
class SimulationRuntime:
    config: simulation_state.SimulationConfig
    manager: Any
    webrtc: WebRTCBroadcaster | None = None
    webrtc_peer_count: int = 0
    frame_callback: Any | None = None
    state_callback: Any | None = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global simulation managers
simulations: Dict[str, SimulationRuntime] = {}
_stream_subscribers: Dict[str, int] = {}
_subscriber_lock = asyncio.Lock()


async def _increment_subscribers(session_id: str) -> int:
    async with _subscriber_lock:
        count = _stream_subscribers.get(session_id, 0) + 1
        _stream_subscribers[session_id] = count
        return count


async def _decrement_subscribers(session_id: str) -> int:
    async with _subscriber_lock:
        count = _stream_subscribers.get(session_id, 0) - 1
        if count <= 0:
            _stream_subscribers.pop(session_id, None)
            return 0
        _stream_subscribers[session_id] = count
        return count


def _create_manager(config: simulation_state.SimulationConfig):
    if config.engine == "mujoco":
        if not MUJOCO_AVAILABLE:
            raise HTTPException(status_code=503, detail="MuJoCo is not available")
        if not config.model_path:
            raise HTTPException(status_code=400, detail="model_path required for MuJoCo")
        return MuJoCoStreamManager(
            model_path=config.model_path,
            width=config.width,
            height=config.height,
            fps=config.fps,
            headless=config.headless,
        )
    if config.engine == "pybullet":
        if not PYBULLET_AVAILABLE:
            raise HTTPException(status_code=503, detail="PyBullet is not available")
        return PyBulletStreamManager(
            urdf_path=config.model_path,
            width=config.width,
            height=config.height,
            fps=config.fps,
            headless=config.headless,
        )
    raise HTTPException(status_code=400, detail=f"Unknown engine: {config.engine}")


def _state_status(is_streaming: bool, fallback: str) -> str:
    return "streaming" if is_streaming else fallback


async def _persist_state(session_id: str, state: dict, *, status: str, streaming: bool) -> None:
    await simulation_state.update_state(
        session_id,
        state,
        status=status,
        streaming=streaming,
    )


def _active_subscribers(session_id: str) -> int:
    return _stream_subscribers.get(session_id, 0)


def _build_frame_callback(session_id: str, runtime: SimulationRuntime):
    async def frame_callback(frame_bytes: bytes) -> None:
        if _active_subscribers(session_id) > 0:
            await simulation_state.publish_frame(session_id, frame_bytes)
        if runtime.webrtc and runtime.webrtc.peer_count > 0:
            await runtime.webrtc.publish_frame(frame_bytes)

    return frame_callback


def _build_state_callback(session_id: str, runtime: SimulationRuntime):
    async def state_callback(state: Dict[str, Any]) -> None:
        await _persist_state(session_id, state, status="streaming", streaming=runtime.manager.is_streaming)

    return state_callback


async def _update_streaming(session_id: str, runtime: SimulationRuntime) -> None:
    should_stream = _active_subscribers(session_id) > 0 or runtime.webrtc_peer_count > 0
    if should_stream and not runtime.manager.is_streaming:
        await runtime.manager.start_streaming(runtime.frame_callback, state_callback=runtime.state_callback)
    elif not should_stream and runtime.manager.is_streaming:
        await runtime.manager.stop_streaming()


async def _ensure_runtime(session_id: str) -> SimulationRuntime:
    runtime = simulations.get(session_id)
    if runtime:
        return runtime
    config = await simulation_state.get_config(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Simulation {session_id} not found")
    manager = _create_manager(config)
    runtime = SimulationRuntime(config=config, manager=manager)
    runtime.frame_callback = _build_frame_callback(session_id, runtime)
    runtime.state_callback = _build_state_callback(session_id, runtime)

    if settings.webrtc_enabled and settings.webrtc_signaling_url:
        async def _on_peer_count(count: int) -> None:
            runtime.webrtc_peer_count = count
            await _update_streaming(session_id, runtime)

        runtime.webrtc = WebRTCBroadcaster(
            settings.webrtc_signaling_url,
            session_id,
            config.fps,
            on_peer_count=_on_peer_count,
        )
        await runtime.webrtc.start()
    simulations[session_id] = runtime
    return runtime


async def _remove_runtime(session_id: str) -> None:
    runtime = simulations.pop(session_id, None)
    if runtime:
        await runtime.manager.stop_streaming()
        runtime.manager.close()
        if runtime.webrtc:
            await runtime.webrtc.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the application."""
    logger.info("Simulation Agent starting up...")
    logger.info(f"MuJoCo available: {MUJOCO_AVAILABLE}")
    logger.info(f"PyBullet available: {PYBULLET_AVAILABLE}")
    await init_redis()
    await session_events.start_listener()
    session_events.register_handler("simulation", handle_session_event)
    try:
        yield
    finally:
        session_events.unregister_handler("simulation")
        await session_events.stop_listener()
        # Cleanup
        logger.info("Simulation Agent shutting down...")
        for session_id in list(simulations.keys()):
            try:
                await _remove_runtime(session_id)
            except Exception as e:
                logger.error(f"Error closing simulation {session_id}: {e}")
        await close_redis()


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
    persisted = await simulation_state.list_session_ids()
    return {
        "status": "healthy",
        "mujoco_available": MUJOCO_AVAILABLE,
        "pybullet_available": PYBULLET_AVAILABLE,
        "active_simulations": len(simulations),
        "persisted_simulations": len(persisted),
    }


@app.get("/sessions/active")
async def list_active_sessions():
    return {"sessions": get_active_sessions()}


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

    if await simulation_state.get_config(session_id):
        raise HTTPException(status_code=400, detail=f"Simulation {session_id} already persisted")

    config = simulation_state.SimulationConfig(
        session_id=session_id,
        engine=request.engine,
        model_path=request.model_path,
        width=request.width,
        height=request.height,
        fps=request.fps,
        headless=request.headless,
    )

    manager = _create_manager(config)
    runtime = SimulationRuntime(config=config, manager=manager)
    runtime.frame_callback = _build_frame_callback(session_id, runtime)
    runtime.state_callback = _build_state_callback(session_id, runtime)

    if settings.webrtc_enabled and settings.webrtc_signaling_url:
        async def _on_peer_count(count: int) -> None:
            runtime.webrtc_peer_count = count
            await _update_streaming(session_id, runtime)

        runtime.webrtc = WebRTCBroadcaster(
            settings.webrtc_signaling_url,
            session_id,
            config.fps,
            on_peer_count=_on_peer_count,
        )

    simulations[session_id] = runtime

    try:
        await simulation_state.persist_config(config)
        state = runtime.manager.get_state()
        await _persist_state(
            session_id,
            state,
            status="created",
            streaming=runtime.manager.is_streaming,
        )
        if runtime.webrtc:
            await runtime.webrtc.start()
        logger.info(f"Created {request.engine} simulation for session {session_id}")
        return {
            "status": "created",
            "session_id": session_id,
            "engine": request.engine,
            "state": state,
        }
    except Exception as e:
        simulations.pop(session_id, None)
        manager.close()
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
    runtime = await _ensure_runtime(session_id)
    state = runtime.manager.get_state()
    await _persist_state(
        session_id,
        state,
        status=_state_status(runtime.manager.is_streaming, "ready"),
        streaming=runtime.manager.is_streaming,
    )
    return state


@app.post("/simulations/{session_id}/control")
async def control_simulation(session_id: str, request: SimulationControlRequest):
    """Control simulation (play, pause, reset, step).
    
    Args:
        session_id: Session identifier
        request: Control action and parameters
    
    Returns:
        Updated simulation state
    """
    runtime = await _ensure_runtime(session_id)
    sim = runtime.manager

    try:
        state_snapshot: Dict[str, Any] | None = None
        streaming_status = sim.is_streaming
        if request.action == "reset":
            result = sim.reset()
            streaming_status = False
            state_snapshot = result
        elif request.action == "step":
            import numpy as np
            actions = np.array(request.actions) if request.actions else None
            result = sim.step(actions)
            state_snapshot = result
        elif request.action == "play":
            result = {"status": "playing", "message": "Use WebSocket for continuous streaming"}
            state_snapshot = sim.get_state()
        elif request.action == "pause":
            await sim.stop_streaming()
            result = {"status": "paused"}
            streaming_status = False
            state_snapshot = sim.get_state()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        if state_snapshot is None:
            state_snapshot = sim.get_state()
        await _persist_state(
            session_id,
            state_snapshot,
            status=request.action,
            streaming=streaming_status,
        )

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
    runtime = await _ensure_runtime(session_id)
    sim = runtime.manager
    
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
    runtime_exists = session_id in simulations
    config_exists = await simulation_state.get_config(session_id)
    if not runtime_exists and not config_exists:
        raise HTTPException(status_code=404, detail=f"Simulation {session_id} not found")

    if runtime_exists:
        await _remove_runtime(session_id)

    await simulation_state.remove_simulation(session_id)
    
    logger.info(f"Deleted simulation {session_id}")
    
    return {"status": "deleted", "session_id": session_id}


# --- WebSocket Streaming ---

@app.websocket("/simulations/{session_id}/stream")
async def stream_simulation(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming simulation frames to multiple clients."""

    try:
        runtime = await _ensure_runtime(session_id)
    except HTTPException:
        await websocket.close(code=1008, reason=f"Simulation {session_id} not found")
        return

    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")

    sim = runtime.manager

    pubsub = await simulation_state.subscribe_frames(session_id)

    async def forward_frames():
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    await asyncio.sleep(0.01)
                    continue
                payload = message.get("data")
                if not payload:
                    continue
                try:
                    frame_bytes = simulation_state.decode_frame_message(payload)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error(f"Invalid frame payload: {exc}")
                    continue
                await websocket.send_bytes(frame_bytes)
        except asyncio.CancelledError:
            pass

    forward_task = asyncio.create_task(forward_frames())
    await _increment_subscribers(session_id)
    await _update_streaming(session_id, runtime)

    try:
        while True:
            message = await websocket.receive_text()
            if message == "pause":
                await sim.stop_streaming()
                await _persist_state(
                    session_id,
                    sim.get_state(),
                    status="paused",
                    streaming=False,
                )
            elif message == "play":
                await _update_streaming(session_id, runtime)
            elif message == "reset":
                await sim.stop_streaming()
                state = sim.reset()
                await _persist_state(
                    session_id,
                    state,
                    status="reset",
                    streaming=False,
                )
            elif message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass
        await simulation_state.close_frame_subscription(pubsub)
        remaining = await _decrement_subscribers(session_id)
        if remaining == 0:
            await _update_streaming(session_id, runtime)


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


# --- C++ Build Agent ---

@app.post("/build")
async def build_cpp(request: Request):
    """Compile C++ source files and optionally run the binary.

    Expects JSON body matching BuildRequest schema.
    Returns BuildResult with compilation output and optional execution result.
    """
    from co_sim.services.build_agent import BuildRequest, compile_cpp, execute_binary, persist_build_status
    import uuid as _uuid

    payload = await request.json()
    build_id = str(_uuid.uuid4())[:8]

    try:
        req = BuildRequest(**payload)
    except Exception as e:
        return {"status": "error", "error": f"Invalid build request: {e}"}

    await persist_build_status(req.workspace_id, build_id, status="building")

    result = await compile_cpp(req)

    await persist_build_status(
        req.workspace_id,
        build_id,
        status=result.status,
        artifact=result.artifact_path,
    )

    response = result.model_dump()
    response["build_id"] = build_id

    # Optionally execute the binary if build succeeded and run=true
    if result.status == "success" and payload.get("run", False) and result.artifact_path:
        exec_result = await execute_binary(result.artifact_path)
        response["execution"] = exec_result

    return response


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
    
    runtime = await _ensure_runtime(session_id)
    sim = runtime.manager
    
    # Debug: Log the code being executed (BEFORE capturing stdout)
    logger.info(f"📝 Executing code (length={len(request.code)})")
    logger.info(f"First 200 chars: {request.code[:200]}")
    
    # Capture stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    captured_stdout = ""
    captured_stderr = ""
    
    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        
        # Test that stdout capture is working
        print("🔧 Starting code execution...")
        sys.stdout.flush()
        
        # Create execution context with simulation API
        context = {
            'sim': sim,
            'np': __import__('numpy'),
            'time': __import__('time'),
            'get_simulation': lambda: sim,  # Alias for CoSim compatibility
            'print': print,  # Explicitly provide print function
            '__name__': '__main__',  # Set __name__ so if __name__ == "__main__" works
        }
        
        # Change working directory if specified
        if request.working_dir and os.path.exists(request.working_dir):
            os.chdir(request.working_dir)
        
        # Execute user code
        exec(request.code, context, context)
        
        print("✅ Code execution finished")
        
        # Force flush to ensure all output is captured
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Get final simulation state (with error handling)
        try:
            final_state = sim.get_state()
        except Exception as e:
            logger.warning(f"Could not get final state: {e}")
            final_state = {"status": "completed", "note": "State unavailable after execution"}
        
        # Debug: Check what we captured (BEFORE restoring stdout)
        captured_stdout = stdout_capture.getvalue()
        captured_stderr = stderr_capture.getvalue()
        
        return {
            "status": "success",
            "stdout": captured_stdout,
            "stderr": captured_stderr,
            "state": final_state,
            "simulation_active": session_id in simulations,
        }
    
    except Exception as e:
        logger.error(f"Code execution error: {e}", exc_info=True)
        captured_stdout = stdout_capture.getvalue()
        captured_stderr = stderr_capture.getvalue()
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "stdout": captured_stdout,
            "stderr": captured_stderr,
        }
    
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
        # Debug log AFTER restoring stdout
        logger.info(f"✅ Execution complete. Captured stdout length: {len(captured_stdout)}, stderr length: {len(captured_stderr)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")
