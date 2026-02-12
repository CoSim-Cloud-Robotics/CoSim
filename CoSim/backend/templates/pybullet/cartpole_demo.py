"""
PyBullet Cartpole Demonstration

This is a default script that runs when you create a new PyBullet project.
It demonstrates a simple cartpole (inverted pendulum) simulation with control.

Features:
- Physics simulation using PyBullet
- Real-time rendering and streaming
- Simple PD controller for balancing
- Customizable parameters

Run this simulation to see it in action!
"""

import numpy as np
import time

# Get simulation instance (provided by CoSim execution context)
sim = get_simulation()

# Simulation parameters
CONTROL_ENABLED = True
KP = 50.0  # Proportional gain
KD = 10.0  # Derivative gain
TARGET_ANGLE = 0.0  # Target angle (upright)

# Run simulation for a duration
SIMULATION_DURATION = 30.0  # seconds
CONTROL_FREQUENCY = 60  # Hz

print("=" * 60)
print("PyBullet Cartpole Simulation")
print("=" * 60)
print(f"Duration: {SIMULATION_DURATION}s")
print(f"Control: {'Enabled' if CONTROL_ENABLED else 'Disabled'}")
print(f"PD Gains: Kp={KP}, Kd={KD}")
print("=" * 60)

# Reset simulation to initial state
initial_state = sim.reset()
print(f"\n✓ Simulation reset")
print(f"  Frame: {initial_state['frame']}")
print(f"  Time: {initial_state['time']:.3f}s")
print(f"  Bodies: {initial_state.get('num_bodies', 'N/A')}")

# Main simulation loop
start_time = time.time()
prev_angle = 0.0
step_count = 0

print("\n🎮 Starting simulation loop...")
print("After execution, connect WebSocket to stream frames to browser...\n")

while True:
    current_time = time.time() - start_time
    if current_time >= SIMULATION_DURATION:
        break
    
    try:
        # Get current state
        state = sim.get_state()
        
        # Calculate control action if enabled
        action = None
        if CONTROL_ENABLED:
            # Simple PD control for cartpole
            # Get pole angle from base orientation
            angle = state.get('base_orientation', [0, 0, 0, 1])[1]  # Approximate
            angle_rate = (angle - prev_angle) * CONTROL_FREQUENCY
            
            # PD control
            error = TARGET_ANGLE - angle
            control_force = KP * error - KD * angle_rate
            
            # Clip force to reasonable range
            control_force = np.clip(control_force, -100, 100)
            
            action = np.array([control_force])
            prev_angle = angle
        
        # Step simulation
        step_result = sim.step(action)
        step_count += 1
        
        # Print progress every 5 seconds
        if step_count % (CONTROL_FREQUENCY * 5) == 0:
            elapsed = step_result['time']
            print(f"  [{elapsed:6.2f}s] Frame {step_result['frame']:4d}")
        
        # Sleep to maintain control frequency
        time.sleep(1.0 / CONTROL_FREQUENCY)
        
    except Exception as e:
        print(f"\n⚠️  Error during simulation step: {e}")
        break

# Final statistics
total_time = time.time() - start_time
print("\n" + "=" * 60)
print("✓ Simulation Complete!")
print("=" * 60)
print(f"Total frames: {step_count}")
print(f"Simulation time: {total_time:.2f}s")
print(f"Average FPS: {step_count / total_time:.1f}")
print("=" * 60)

print("\n💡 Next steps:")
print("  1. Connect WebSocket to view live streaming")
print("  2. Modify control gains (KP, KD) to see different behaviors")
print("  3. Change SIMULATION_DURATION to run longer")
print("  4. Implement your own controller algorithm")
print("  5. Add your custom URDF models")
print("\n🚀 Simulation ready for streaming!")
