#!/bin/bash

echo "Testing Simulation Agent..."
echo ""

echo "1. Health Check:"
curl -s http://localhost:8005/health | python3 -m json.tool
echo ""

echo "2. Creating PyBullet simulation:"
curl -s -X POST http://localhost:8005/simulations/create \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session",
    "engine": "pybullet",
    "model_path": "/app/templates/pybullet/cartpole.urdf",
    "width": 640,
    "height": 480,
    "fps": 30,
    "headless": true
  }' | python3 -m json.tool
echo ""

echo "3. Checking health again (should show 1 active simulation):"
curl -s http://localhost:8005/health | python3 -m json.tool
echo ""

echo "4. Testing WebSocket connection (wscat required):"
echo "   Run: wscat -c ws://localhost:8005/simulations/test-session/stream"
echo "   Then type: play"
echo ""
