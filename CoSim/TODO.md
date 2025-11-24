# CoSim TODOs (near-term)

- [ ] Simulator: validate end-to-end create/control/stream flows; align frontend with Redis-backed sim state and fix any breakages.
- [ ] Integration tests: stand up Postgres + Redis harness and add E2E session transition/event fan-out tests (unblocks `test_auth0_exchange.py`/session coverage).
- [ ] Frontend wiring: pass `conversation_id` in chatbot client/UI to exercise Redis-backed history; sanity check multi-instance Yjs awareness with the Redis-persistent collab server.
- [ ] WebRTC signaling: add multi-agent smoke tests to verify Redis relay fan-out across nodes.
- [ ] Ops: bring up updated `docker-compose` (Redis volume/commander) to confirm health; document production Redis hardening (auth/AOF/metrics) and update docs accordingly.
