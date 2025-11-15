# Simulation System Fixes - November 15, 2025

## Issues Fixed

### 1. PyBullet State Error Handling ✅
**Problem:** `getBasePositionAndOrientation` and `getNumBodies` would crash when physics client disconnected or robot was removed.

**Solution:** Added try-catch error handling in `pybullet_env.py` `get_state()` method:
```python
try:
    state["num_bodies"] = p.getNumBodies()
except Exception:
    state["num_bodies"] = 0

try:
    base_pos, base_orn = p.getBasePositionAndOrientation(self.robot_id)
    # ... get state
except Exception as e:
    logger.warning(f"Could not get robot state: {e}")
    state["robot_id"] = None
```

**Files Changed:**
- `backend/src/co_sim/agents/simulation/pybullet_env.py`

---

### 2. Infinite Loop Demo Code ✅
**Problem:** Autoplay code used daemon threads with infinite `while True:` loops that never completed, causing issues with code execution completion detection.

**Solution:** Replaced infinite loops with finite duration (30 seconds) simulations:
```python
# OLD: while True: ...
# NEW:
DURATION = 30.0
start_time = time.time()
while (time.time() - start_time) < DURATION:
    # simulation code with error handling
    try:
        # ... step simulation
    except Exception as e:
        print(f"Error: {e}")
        break
```

**Files Changed:**
- `frontend/src/routes/Workspace.tsx` - Both `PYBULLET_AUTOPLAY_CODE` and `MUJOCO_AUTOPLAY_CODE`
- `backend/templates/pybullet/cartpole_demo.py`

---

### 3. WebSocket Connection Timing ✅
**Problem:** WebSocket tried to connect immediately after code execution, sometimes before simulation was fully ready.

**Solution:** Added 1-second delay before connecting to ensure simulation is ready:
```typescript
// Small delay to ensure simulation is ready
const timer = setTimeout(() => {
  console.log('🔌 Connecting to WebSocket stream...');
  connectWebSocket();
}, 1000);
```

**Files Changed:**
- `frontend/src/components/SimulationViewer.tsx`

---

### 4. Simulation Lifecycle Management ✅
**Problem:** After code execution, trying to get final state could crash if physics client was disconnected.

**Solution:** Added error handling around final state retrieval:
```python
try:
    final_state = sim.get_state()
except Exception as e:
    logger.warning(f"Could not get final state: {e}")
    final_state = {"status": "completed", "note": "State unavailable after execution"}
```

**Files Changed:**
- `backend/src/co_sim/agents/simulation/main.py`

---

### 5. Session Conflict When Switching Engines ✅
**Problem:** When switching from PyBullet to MuJoCo (or vice versa), the system tried to create a new simulation with the same session ID, resulting in "Simulation already exists" error.

**Solution:** Added automatic cleanup of existing simulation before creating new one:
```typescript
// Delete any existing simulation for this session first
try {
  await fetch(`${simulationApiUrl}/simulations/${sessionIdForSim}`, {
    method: 'DELETE',
    // ...
  });
  console.log('✓ Previous simulation deleted');
} catch (deleteError) {
  console.log('ℹ️ No previous simulation to delete (this is okay)');
}
```

**Files Changed:**
- `frontend/src/routes/Workspace.tsx`

---

## Testing

### Quick Test
1. Open browser to http://localhost:5173
2. Navigate to a PyBullet project
3. Simulation should auto-create and start streaming
4. Switch to a MuJoCo project
5. Old simulation should be deleted, new one created
6. Both should stream frames successfully

### Detailed Test Script
Run: `./test-simulation-flow.sh`

This script tests:
- Health check
- Simulation creation
- Code execution
- State retrieval
- Cleanup

---

## Architecture Notes

### Simulation Flow
1. **Create**: `POST /simulations/create` - Creates simulation instance in memory
2. **Execute**: `POST /simulations/{id}/execute` - Runs Python code in simulation context
3. **Stream**: `WebSocket /simulations/{id}/stream` - Streams frames at target FPS
4. **Delete**: `DELETE /simulations/{id}` - Cleanup simulation

### Key Components
- **Simulation Agent** (`simulation-agent:8005`): Manages MuJoCo/PyBullet instances
- **Frontend** (`web:5173`): React UI with Monaco editor and WebSocket streaming
- **SimulationViewer**: Canvas-based frame rendering from WebSocket
- **Workspace**: Orchestrates simulation creation and code execution

---

## Known Limitations

1. **Session Persistence**: Simulations are stored in-memory, lost on container restart
2. **Single Session**: Using `default-session` for all workspaces (should be workspace-specific)
3. **No Save/Resume**: Simulation state is not persisted between sessions
4. **Fixed Duration**: Demo code runs for fixed 30 seconds (could be configurable)

---

## Future Improvements

1. **Per-Workspace Sessions**: Use workspace ID as session ID
2. **Database Persistence**: Store simulation metadata in database
3. **Session Resume**: Allow reconnecting to running simulations
4. **Multiple Engines**: Run MuJoCo and PyBullet simultaneously
5. **Better Error Recovery**: Auto-restart failed simulations
6. **Resource Limits**: CPU/GPU quotas per simulation
7. **Recording**: Save simulation runs for replay

---

## Deployment Notes

### Containers Updated
- `simulation-agent` - Backend simulation engine
- `web` - Frontend React application

### Build Commands
```bash
docker-compose build simulation-agent web
docker-compose restart simulation-agent web
```

### Verify Status
```bash
docker-compose ps
docker-compose logs simulation-agent --tail=20
curl http://localhost:8005/health
```

---

## Contact

For issues or questions about these fixes, refer to the commit history on branch `sim-setup`.

**Status**: ✅ All fixes deployed and tested
**Date**: November 15, 2025
