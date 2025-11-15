# Auto-Play Cartpole Feature

## Overview
The workspace now automatically starts playing a cartpole simulation when a user creates or opens a new project. This provides an immediate, engaging demonstration of the platform's capabilities.

## Implementation Details

### Frontend Changes (`frontend/src/routes/Workspace.tsx`)

1. **State Management**
   - Added `hasAutoPlayed` state variable to track if auto-play has been triggered
   - Prevents multiple auto-play attempts in the same session

2. **Auto-Play Logic**
   - New `useEffect` hook that triggers when workspace loads
   - Checks for required conditions:
     - Project exists
     - Active workspace available
     - User token present
     - Active session ID available
     - Has not already auto-played

3. **Engine-Specific Code**
   - Detects the simulation engine from project settings (MuJoCo or PyBullet)
   - Loads appropriate cartpole demo code for each engine
   - **MuJoCo**: PD controller that continuously balances the pole, with automatic reset on failure
   - **PyBullet**: Control loop with physics simulation and frame rendering

4. **Execution Flow**
   ```typescript
   useEffect(() => {
     if (hasAutoPlayed || !project || !activeWorkspaceId || !token || !activeSessionId) {
       return;
     }

     const loadAndPlayDemo = async () => {
       // 1. Detect engine (mujoco or pybullet)
       const engine = project.settings?.engine || 'mujoco';
       
       // 2. Load appropriate demo code
       const demoCode = engine === 'pybullet' ? pybulletCode : mujocoCode;
       
       // 3. Set code in state (makes it visible in IDE)
       setCurrentSimulationCode(demoCode);
       
       // 4. Wait for UI/session to be ready (1.5s)
       await new Promise(resolve => setTimeout(resolve, 1500));
       
       // 5. Run the simulation
       await handleRunSimulation(demoCode);
       
       // 6. Mark as completed
       setHasAutoPlayed(true);
     };

     loadAndPlayDemo();
   }, [project, activeWorkspaceId, token, hasAutoPlayed, activeSessionId]);
   ```

## Demo Code Features

### MuJoCo Cartpole
- **Continuous simulation**: Runs indefinitely with automatic resets
- **PD Controller**: Balances the pole using proportional-derivative control
- **Self-healing**: Automatically resets when pole falls (angle > 0.5 rad)
- **Progress updates**: Prints status every 50 steps and milestone every 1000 steps
- **Real-time streaming**: Frames streamed via WebSocket at 60 FPS

### PyBullet Cartpole
- **Physics simulation**: Full PyBullet physics engine
- **Control loop**: 60 Hz control frequency
- **State monitoring**: Tracks robot position and orientation
- **Visual feedback**: Real-time frame rendering to browser
- **Progress logging**: Periodic status updates every second

## User Experience

1. **Login/Create Project** → User authenticates via Auth0
2. **Workspace Loads** → Auto-play logic detects new workspace
3. **Demo Starts** → Cartpole simulation begins automatically after 1.5s
4. **Visual Feedback** → User immediately sees:
   - Simulation running in the viewer panel
   - Live video stream of the cartpole balancing
   - Console output showing control progress
   - Code visible in the IDE editor

## Benefits

✅ **Immediate Engagement**: Users see results instantly, no setup required  
✅ **Engine Agnostic**: Works with both MuJoCo and PyBullet  
✅ **Educational**: Demonstrates PD control and continuous simulation loops  
✅ **Performance**: Uses optimized continuous loops for smooth 60 FPS streaming  
✅ **Reliable**: Error handling prevents crashes, allows retry on failure  

## Technical Notes

- **Timing**: 1.5 second delay ensures session and WebSocket are ready
- **Error Handling**: Failures don't prevent future attempts (resets `hasAutoPlayed`)
- **Session Dependency**: Requires valid session ID to connect WebSocket stream
- **Code Injection**: Uses `get_simulation()` API provided by CoSim execution context
- **Browser Console**: Auto-play status logged for debugging

## Testing

To test the auto-play feature:

1. Start the Docker containers: `docker-compose up -d`
2. Navigate to `http://localhost:5173`
3. Login via Auth0
4. Open or create a project
5. Wait ~2 seconds after workspace loads
6. You should see:
   - Simulation viewer showing cartpole animation
   - Console output in the logs panel
   - Code loaded in the IDE editor

## Configuration

Auto-play behavior can be customized by modifying:
- **Delay**: Change `setTimeout(resolve, 1500)` for different wait time
- **Demo Code**: Edit `mujocoCode` or `pybulletCode` constants
- **Trigger Conditions**: Modify the `useEffect` dependency array
- **Engine Selection**: Controlled by `project.settings.engine`

## Future Enhancements

Potential improvements:
- [ ] Add user preference to disable auto-play
- [ ] Show "Demo Running" indicator in UI
- [ ] Allow selection of different demo scenarios
- [ ] Pre-load demo templates from backend
- [ ] Add pause/resume controls for demo
- [ ] Create demo library with multiple examples
