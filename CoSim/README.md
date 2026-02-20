# CoSim Platform - Complete Web IDE for Robotics Development

A cloud-based collaborative robotics development platform with browser IDE, supporting **Python & C++**, real-time multi-user editing, integrated terminal, and simulation viewer.

## Overview

CoSim provides a complete development environment for robotics workflows (SLAM & RL training) with MuJoCo and PyBullet simulators, all accessible through your browser.

### Key Features

- **Monaco Editor** - VS Code-quality editing with IntelliSense
- **Real-time Collaboration** - Multiple users edit simultaneously (Yjs CRDT)
- **Integrated Terminal** - Run Python, compile C++, execute commands
- **Simulation Viewer** - WebRTC streaming for MuJoCo/PyBullet
- **File Tree Navigator** - Full project structure browsing
- **Flexible Layouts** - Choose your workspace configuration

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Infrastructure                                           │
│  • PostgreSQL (:5433) - Database                         │
│  • Redis (:6380) - Cache & queues                        │
│  • NATS (:4222) - Event bus                              │
│  • Yjs WebSocket (:1234) - Collaboration                 │
│                                                           │
│  Backend Microservices                                    │
│  • API Gateway (:8080) - Single entry point              │
│  • Auth Agent - JWT, RBAC, OIDC                          │
│  • Project/Workspace Agent - Project management          │
│  • Session Orchestrator - Pod lifecycle                  │
│  • Collab Agent - Document sync                          │
│                                                           │
│  Frontend Web IDE (:5173)                                │
│  ┌──────────────────────────────────────────────┐       │
│  │ File Tree │ Monaco Editor  │  Sim Viewer   │       │
│  │           │ (Python/C++)   │  (WebRTC)     │       │
│  ├──────────────────────────────────────────────┤       │
│  │    Terminal (xterm.js)     │  Controls      │       │
│  └──────────────────────────────────────────────┘       │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Web IDE Features

### Monaco Editor

- Full VS Code editing experience in browser
- Python & C++ syntax highlighting
- IntelliSense & auto-completion
- Error detection & linting
- Multi-cursor editing
- Keyboard shortcuts (Ctrl+S to save, etc.)

### File Tree

- Hierarchical project structure
- Navigate Python (.py) and C++ (.cpp) files
- Visual file type indicators
- Expand/collapse folders
- Click to open in editor

### Real-time Collaboration

- **Yjs CRDT** for conflict-free editing
- Multiple users edit the same file simultaneously
- Automatic conflict resolution
- Per-file collaboration rooms
- Presence awareness (coming soon)

### Integrated Terminal

- Full **xterm.js** terminal emulator
- Execute Python scripts: `python src/main.py`
- Compile C++: `g++ src/main.cpp -o build/main`
- CMake support: `cmake -B build && cmake --build build`
- Color-coded output
- 1000-line scrollback buffer

### Simulation Viewer

- WebRTC video streaming
- MuJoCo & PyBullet support
- Controls: Play, Pause, Reset, Step
- Adjustable FPS (30/60/120)
- Real-time frame display

### Layout Modes

1. **Editor Only** - Maximum focus
2. **With Terminal** - Code + terminal horizontal split
3. **With Simulation** - Code + sim viewer
4. **Full** - Everything visible (default)

## Tech Stack

### Frontend

- **React 18** + **TypeScript**
- **Monaco Editor** (VS Code engine)
- **Yjs** + **y-websocket** + **y-monaco** (collaboration)
- **xterm.js** (terminal)
- **React Router** (navigation)
- **Zustand** (state)
- **TanStack Query** (data fetching)
- **Vite** (build tool)

### Backend

- **FastAPI** (Python)
- **PostgreSQL** (database)
- **Redis** (cache/queues)
- **NATS** (events)
- **gRPC** (inter-service)
- **JWT** (auth)

### Infrastructure

- **Docker** + **Docker Compose**
- **WebRTC** (streaming)
- **Yjs** (CRDT sync)
