# Redis Integration Plan

This document tracks the incremental adoption of Redis across the CoSim platform.
Each section lists actionable tasks with their current completion state.

## Legend

- [ ] Not started
- [~] In progress
- [x] Complete

## 1. Shared Client Layer

- [x] Add `co_sim.core.redis` helper providing async Redis clients, FastAPI dependencies, and lifecycle hooks.
- [x] Ensure every agent app wires the helper during startup/shutdown and exposes helper utilities (TTL cache, locks, pub/sub helpers).
- [x] Extend backend tests to spin up/point to disposable Redis using `COSIM_REDIS_URL` for deterministic coverage.

## 2. API Gateway Caching & Rate Limits

- [x] Cache read-heavy proxy GET responses with short TTL keys.
- [x] Replace in-memory rate limiting with Redis-backed token buckets keyed by user/IP and surface `429`s when exceeded.
- [x] Add regression tests verifying cache hits and throttling behaviour.

## 3. Auth/Token Hardening

- [x] Persist login attempt counters for `/v1/auth/token` (username + IP throttling via Redis).
- [x] Store verification codes and refresh tokens in Redis for Auth/Auth0 flows.
- [x] Maintain a Redis-backed token blacklist/allowlist consulted in `co_sim.services.token`.
- [x] Add tests for login throttling, token revocation, refresh rotation, and verification codes.

## 4. Session Orchestrator Enhancements

- [x] Mirror hot session metadata in Redis hashes/sets to reduce Postgres reads.
- [x] Push lifecycle events over Redis pub/sub so other agents can subscribe without polling (collab + simulation agents consume events).
- [~] Validate with integration tests covering session transitions and event fan-out (unit + listener suites running; full E2E still blocked by missing local Postgres/Redis services).

## 5. Simulation Agent State Sharing

- [x] Replace the in-process `simulations` dict with Redis data structures for resumable runs (`co_sim.services.simulation_state` now owns persisted configs/state).
- [x] Use Redis pub/sub channels for WebSocket fan-out and graceful shutdown coordination (simulation streams publish frames to Redis and multiplex subscribers).
- [x] Add tests (and/or fakes) to prove state survives restarts and multiple subscribers (`tests/test_simulation_state.py`).

## 6. Collaboration & WebRTC Services

- [x] Add Redis-backed persistence/awareness to the Yjs collaboration server for multi-instance resilience (redis persistence + awareness relay in `collab-server`).
- [x] Move WebRTC signaling `rooms` and `clients` to Redis to support horizontal scaling (`webrtc-signaling/stateStore.js` + server wiring persist rooms/clients/heartbeats + Redis relay pub/sub for cross-node signaling).
- [x] Provide smoke tests or scripted checks to ensure state cleanup on disconnects (`node --test tests/stateStore.test.js` now covers Redis bookkeeping; multi-agent smoke tests still pending).

## 7. Chatbot Memory & Rate Control

- [x] Cache chat history and embedding lookups in Redis for cross-instance continuity (chat API persists per-conversation transcripts; vector queries are cached).
- [x] Store warmup flags/locks for the vector store to avoid duplicate initialization work (Redis-backed warmup lock + readiness flag).
- [x] Cover the new flows with service-level tests (`backend/services/chatbot/tests/test_redis_cache.py`).

## 8. Container & DevOps Enhancements

- [x] Harden the `redis` service in `docker-compose.yml` (volumes, health checks, redis-commander access).
- [x] Ensure `.env` files document `COSIM_REDIS_URL` and add helper commands in `docker-manager.sh` for seeding/resetting Redis.
- [x] Update internal docs to describe local + production Redis management (README Redis section).

---

### Next Step

Remaining gap: end-to-end session-orchestrator integration tests are still limited because `test_auth0_exchange.py` requires a live Postgres instance; once infra is available, expand validation beyond the targeted suites listed below.

**Recent validation:**
- `cd backend && PYTHONPATH=src pytest tests/test_simulation_state.py`
- `cd backend && PYTHONPATH=src pytest tests/test_session_events.py`
- `cd backend && PYTHONPATH=src pytest tests/test_collab_service.py`
- `cd webrtc-signaling && npm test`
- `cd collab-server && npm test`
- `cd backend/services/chatbot && python -m pytest tests/test_redis_cache.py`
