#!/bin/bash

echo "========================================"
echo "CoSim Simulation Flow Test"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SESSION_ID="test-session-$(date +%s)"

echo -e "${YELLOW}Testing with session ID: ${SESSION_ID}${NC}"
echo ""

# Step 1: Health Check
echo "Step 1: Checking simulation agent health..."
HEALTH=$(curl -s http://localhost:8005/health)
echo "$HEALTH" | python3 -m json.tool
if echo "$HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓ Health check passed${NC}"
else
    echo -e "${RED}✗ Health check failed${NC}"
    exit 1
fi
echo ""

# Step 2: Create Simulation
echo "Step 2: Creating PyBullet simulation..."
CREATE_RESPONSE=$(curl -s -X POST http://localhost:8005/simulations/create \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"${SESSION_ID}\",
    \"engine\": \"pybullet\",
    \"model_path\": \"/app/templates/pybullet/cartpole.urdf\",
    \"width\": 640,
    \"height\": 480,
    \"fps\": 30,
    \"headless\": true
  }")

echo "$CREATE_RESPONSE" | python3 -m json.tool

if echo "$CREATE_RESPONSE" | grep -q "created"; then
    echo -e "${GREEN}✓ Simulation created successfully${NC}"
else
    echo -e "${RED}✗ Simulation creation failed${NC}"
    exit 1
fi
echo ""

# Step 3: Verify simulation exists
echo "Step 3: Verifying simulation exists..."
HEALTH2=$(curl -s http://localhost:8005/health)
echo "$HEALTH2" | python3 -m json.tool
if echo "$HEALTH2" | grep -q '"active_simulations":1'; then
    echo -e "${GREEN}✓ Simulation is active${NC}"
else
    echo -e "${RED}✗ Simulation not found in active list${NC}"
fi
echo ""

# Step 4: Execute test code
echo "Step 4: Executing test code..."
TEST_CODE='
import time
import numpy as np

sim = get_simulation()

print("Test: Resetting simulation...")
state = sim.reset()
print(f"  Reset successful: frame={state[\"frame\"]}, time={state[\"time\"]}")

print("Test: Running 5 steps...")
for i in range(5):
    result = sim.step(np.array([0.0]))
    print(f"  Step {i+1}: frame={result[\"frame\"]}")
    time.sleep(0.1)

print("Test: Getting final state...")
final = sim.get_state()
print(f"  Final state: frame={final[\"frame\"]}, running={final[\"is_running\"]}")

print("Test completed successfully!")
'

EXEC_RESPONSE=$(curl -s -X POST "http://localhost:8005/simulations/${SESSION_ID}/execute" \
  -H "Content-Type: application/json" \
  -d "{\"code\": $(echo "$TEST_CODE" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")}")

echo "$EXEC_RESPONSE" | python3 -m json.tool

if echo "$EXEC_RESPONSE" | grep -q '"status":"success"'; then
    echo -e "${GREEN}✓ Code execution successful${NC}"
    echo ""
    echo "STDOUT:"
    echo "$EXEC_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('stdout', ''))"
else
    echo -e "${RED}✗ Code execution failed${NC}"
    echo "$EXEC_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('stderr', ''))"
fi
echo ""

# Step 5: Verify simulation still exists
echo "Step 5: Verifying simulation persists after execution..."
HEALTH3=$(curl -s http://localhost:8005/health)
if echo "$HEALTH3" | grep -q '"active_simulations":1'; then
    echo -e "${GREEN}✓ Simulation still active after execution${NC}"
else
    echo -e "${YELLOW}⚠ Simulation may have been cleaned up${NC}"
fi
echo ""

# Step 6: Cleanup
echo "Step 6: Cleaning up test simulation..."
curl -s -X DELETE "http://localhost:8005/simulations/${SESSION_ID}"
echo -e "${GREEN}✓ Cleanup complete${NC}"
echo ""

echo "========================================"
echo -e "${GREEN}Test flow completed!${NC}"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Open browser to http://localhost:5173"
echo "2. Navigate to a PyBullet or MuJoCo project"
echo "3. The simulation should auto-play the demo"
echo "4. WebSocket should connect and stream frames"
echo ""
