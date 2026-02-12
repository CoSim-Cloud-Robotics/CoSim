# CoSim Platform - Complete Web IDE for Robotics Development

A cloud-based collaborative robotics development platform with browser IDE, supporting **Python & C++**, real-time multi-user editing, integrated terminal, and simulation viewer.

## 🎯 Overview

CoSim provides a complete development environment for robotics workflows (SLAM & RL training) with MuJoCo and PyBullet simulators, all accessible through your browser.

### Key Features

- 🎨 **Monaco Editor** - VS Code-quality editing with IntelliSense
- 👥 **Real-time Collaboration** - Multiple users edit simultaneously (Yjs CRDT)
- 🖥️ **Integrated Terminal** - Run Python, compile C++, execute commands
- 🤖 **Simulation Viewer** - WebRTC streaming for MuJoCo/PyBullet
- 📁 **File Tree Navigator** - Full project structure browsing
- 🎯 **Flexible Layouts** - Choose your workspace configuration
- 🔒 **Enterprise Ready** - JWT auth, RBAC, session isolation
- 🐳 **Docker Everything** - One command to start the entire stack

## 🚀 Quick Start (< 5 minutes)

```bash
# Clone repository
git clone <your-repo-url>
cd CoSim

# Start all services
./docker-manager.sh start

# Open browser
open http://localhost:5173
```

That's it! You now have:
- ✅ Web IDE with file tree, editor, terminal, sim viewer
- ✅ Real-time collaboration server (Yjs)
- ✅ Backend API services (auth, projects, sessions)
- ✅ Infrastructure (Postgres, Redis, NATS)

See [QUICKSTART.md](./QUICKSTART.md) for detailed walkthrough.

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART.md](./QUICKSTART.md) | 5-minute getting started guide |
| [DOCKER.md](./DOCKER.md) | Complete Docker setup & troubleshooting |
| [AGENT.md](./AGENT.md) | System architecture & microservices |
| [IDE_IMPLEMENTATION.md](./IDE_IMPLEMENTATION.md) | Implementation details & features |
| [frontend/README_IDE.md](./frontend/README_IDE.md) | IDE user guide & features |

## 🏗️ Architecture

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

## 🎨 Web IDE Features

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

## 🛠️ Development

### Using Docker (Recommended)

```bash
# Start all services
./docker-manager.sh start

# View logs
./docker-manager.sh logs web

# Open shell in container
./docker-manager.sh shell web

# Check health
./docker-manager.sh health

# Stop everything
./docker-manager.sh stop
```

### Redis Management

- Docker Compose exposes Redis on `localhost:6380` with append-only persistence and a built-in health check.
- Redis Commander is available at [http://localhost:8081](http://localhost:8081) for browsing keys during development.
- Use `./docker-manager.sh redis cli` to run `redis-cli`, `./docker-manager.sh redis flush` to clear local keys, and `./docker-manager.sh redis stats` for quick INFO output.
- Services read their connection string from `COSIM_REDIS_URL` (defined in `.env.example`); override it if you run an external Redis instance.

### Local Development (Frontend Only)

```bash
cd frontend
npm install
npm run dev
```

Note: You'll need backend services running separately.

## 🎮 Try It Out

1. **Start the stack**: `./docker-manager.sh start`
2. **Open IDE**: http://localhost:5173
3. **Login**: Use demo credentials (see below)
4. **Create Project**: Click "New Project"
5. **Start Session**: Launch a coding session
6. **Edit Code**: Select files from tree, edit in Monaco
7. **Run Code**: Use terminal to execute
8. **Collaborate**: Open in another browser, edit together!

### Demo Credentials

```bash
# First, seed the admin user
cd backend
PYTHONPATH=src python -m co_sim.scripts.seed_admin
```

Then login with:
- **Email**: `admin@cosim.dev`
- **Password**: `adminadmin`

Or create your own account via self-service registration.

## 📦 Tech Stack

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
- **Kubernetes** (production)
- **WebRTC** (streaming)
- **Yjs** (CRDT sync)

## 🔧 Configuration

### Environment Variables

Frontend (`.env`):
```bash
VITE_API_BASE_URL=/api
VITE_COLLAB_WS_URL=ws://localhost:1234
VITE_WEBRTC_SIGNALING_URL=ws://localhost:3000
```

Backend (`docker-compose.yml`):
```yaml
COSIM_DATABASE_URI=postgresql+asyncpg://cosim:cosim@postgres:5432/cosim
COSIM_JWT_SECRET_KEY=supersecretvaluewith32chars000000
COSIM_REDIS_URL=redis://redis:6379/0
COSIM_NATS_URL=nats://nats:4222
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| IDE not loading | `./docker-manager.sh logs web` |
| Ports in use | Edit `docker-compose.yml` port mappings |
| Collab not working | Check `curl http://localhost:1234/health` |
| Database errors | `./docker-manager.sh db connect` |
| Build errors | `./docker-manager.sh rebuild web` |

Full troubleshooting guide in [DOCKER.md](./DOCKER.md).

## 📊 Service Ports

| Service | Port | URL |
|---------|------|-----|
| Web IDE | 5173 | http://localhost:5173 |
| API Gateway | 8080 | http://localhost:8080 |
| API Docs | 8080 | http://localhost:8080/docs |
| Yjs Collab | 1234 | ws://localhost:1234 |
| PostgreSQL | 5433 | postgresql://localhost:5433 |
| Redis | 6380 | redis://localhost:6380 |
| NATS | 4222 | nats://localhost:4222 |
| NATS Monitoring | 8222 | http://localhost:8222 |

## 🧪 Testing

```bash
# Frontend tests
docker-compose exec web npm test

# Backend tests
docker-compose exec api-gateway pytest

# Check types
docker-compose exec web npm run build
```

## 🚀 Production Deployment

See [DOCKER.md](./DOCKER.md) for production deployment with:
- HTTPS/TLS
- Secrets management
- Horizontal scaling
- Monitoring & logging
- Backup strategies

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📄 License

See LICENSE file for details.

## 🎉 What's Next?

### Current (MVP Complete) ✅
- [x] Monaco editor with Python & C++
- [x] File tree navigation
- [x] Real-time collaboration (Yjs)
- [x] Integrated terminal
- [x] Simulation viewer UI
- [x] Docker environment
- [x] Backend microservices

### Coming Soon
- [ ] WebRTC simulation streaming (backend)
- [ ] Live presence cursors
- [ ] File create/delete/rename
- [ ] Debugger integration (lldb/gdb, debugpy)
- [ ] Git integration
- [ ] Jupyter notebook support

### Future
- [ ] Extensions marketplace
- [ ] Voice chat
- [ ] Screen sharing
- [ ] Custom themes
- [ ] VR/XR support

## 💡 Tips

- Press `Ctrl+S` (or `Cmd+S`) to save files
- Try editing with multiple browsers simultaneously
- Use `./docker-manager.sh health` to check all services
- Check API docs at http://localhost:8080/docs
- View collaboration health at http://localhost:1234/health

## 🆘 Need Help?

- Check [DOCKER.md](./DOCKER.md) for troubleshooting
- View logs: `./docker-manager.sh logs [service]`
- Open an issue on GitHub
- Read the architecture docs in [AGENT.md](./AGENT.md)

---

**Built with ❤️ for robotics developers**

Start developing: `./docker-manager.sh start` → http://localhost:5173 🚀
