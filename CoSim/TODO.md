# CoSim TODOs

## Completed

- [x] Redis integration across all services (shared client, caching, pub/sub, session state, simulation state, collab persistence, chatbot memory)
- [x] End-to-end simulation pipeline: Monaco editor → code execution → PyBullet/MuJoCo rendering → WebSocket frame streaming
- [x] Auth0 OIDC integration with JWT token exchange, refresh rotation, and Redis-backed blacklist
- [x] Real-time collaboration via Yjs CRDT with Redis-backed persistence and awareness relay
- [x] WebRTC signaling with Redis-backed room/client state for horizontal scaling
- [x] API Gateway with Redis-cached responses and rate limiting
- [x] Docker Compose stack with health checks, volumes, and redis-commander

### Phase 1 — Core Platform Hardening ✅ (completed via TDD — 41 tests)

- [x] **C++ Build Agent**: `build_agent.py` service — async g++/clang++ compilation, multi-file builds, compile_commands.json, binary execution, Redis build status persistence; gateway wired `POST /runs/build` → simulation agent `/build`
- [x] **Terminal backend**: `terminal.py` service — PTY-backed `TerminalSession` (start/stop/write/read/resize/interrupt), `TerminalManager` (multi-session), Redis state; WebSocket endpoint `ws /v1/sessions/{id}/terminal` in session-orchestrator
- [x] **File persistence**: Workspace file CRUD already fully wired (auto-save at 3s in SessionIDE, `workspace_files.py` service, API routes, gateway routing); verified with 10 SQLite-backed unit tests
- [x] **Error handling & reconnection**: `ws_reconnect.py` — `ReconnectPolicy` (exponential backoff + jitter), `ReconnectManager` (state machine), Redis state; frontend `Terminal.tsx` updated with 10-attempt reconnect; `SimulationViewer` already had reconnect; y-websocket handles it natively
- [x] **Production database migrations**: `scripts/migrate.sh` with migrate/rollback/check/status/dry-run/ci/new subcommands; 7 existing numbered Alembic migrations verified

## Next Steps

### Phase 2 — Simulation & Workflows

- [ ] **RL training agent**: Build the RL Agent for parallel env orchestration, experience collection, and checkpoint management (SB3/JAX/PyTorch)
- [ ] **SLAM pipeline agent**: Implement SLAM Agent with dataset mounting, trajectory alignment, and ATE/RPE metrics
- [ ] **Simulation templates**: Create one-click project templates for RL (MuJoCo PPO, PyBullet PPO) and SLAM (ORB-SLAM2 baseline)
- [ ] **GPU scheduling**: Add GPU node support with resource requests/limits and cost-guard policies
- [ ] **Snapshot & restore**: Implement workspace snapshots (source + env lockfiles + data refs) for reproducibility

### Phase 3 — Collaboration & UX

- [ ] **Presence indicators**: Show collaborator cursors and selections in the Monaco editor with user avatars
- [ ] **Live sim control**: Shared `sim-control.json` via CRDT so collaborators can jointly start/stop/reset/seed simulations
- [ ] **Debugger integration**: Wire debugpy (Python) and gdb/lldb (C++) through the terminal for step-through debugging
- [ ] **TensorBoard streaming**: Pipe RL training metrics to an embedded TensorBoard viewer in the workspace
- [ ] **Chatbot improvements**: Add streaming responses, conversation branching, and context-aware code suggestions

### Phase 4 — Production & Scale

- [ ] **Kubernetes deployment**: Migrate from Docker Compose to K8s manifests with Helm charts, node pools (cpu/gpu), and network policies
- [ ] **CI/CD pipeline**: GitHub Actions for image builds, E2E tests, signed images (cosign), and SBOMs
- [ ] **Observability stack**: Prometheus + Grafana dashboards, OpenTelemetry tracing, Loki log aggregation
- [ ] **Billing & quotas**: Implement Billing Agent (Stripe integration) and Cost Guard Agent (GPU concurrency limits, spend caps)
- [ ] **Security hardening**: mTLS between services, seccomp/AppArmor profiles, KMS-encrypted secrets, abuse/mining detection
- [ ] **Multi-region**: Regional data residency, CDN for static assets, edge caching
