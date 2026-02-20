from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from co_sim.api.v1.routes import sessions
from co_sim.core import logging as logging_config
from co_sim.core.redis import close_redis, init_redis
from co_sim.services.terminal import (
    TerminalManager,
    persist_terminal_state,
    remove_terminal_state,
)

logger = logging.getLogger(__name__)

# Shared terminal manager
_terminal_manager = TerminalManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging_config.configure_logging()
    await init_redis()
    try:
        yield
    finally:
        await _terminal_manager.destroy_all()
        await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(title="CoSim Session Orchestrator", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": "session-orchestrator"}

    # --- Terminal WebSocket ---

    @app.websocket("/v1/sessions/{session_id}/terminal")
    async def terminal_ws(websocket: WebSocket, session_id: str):
        """WebSocket endpoint that bridges the browser xterm.js to a server PTY.

        Protocol (JSON messages):
            Client → Server:
                {"type": "command", "data": "<text>"}   — write to PTY stdin
                {"type": "resize", "rows": N, "cols": M} — resize PTY
                {"type": "interrupt"}                    — send SIGINT
            Server → Client:
                {"type": "output", "data": "<text>"}     — PTY stdout
                {"type": "error", "message": "<text>"}   — error info
        """
        await websocket.accept()

        try:
            ts = await _terminal_manager.get_or_create(session_id)
            if ts.pid:
                await persist_terminal_state(session_id, pid=ts.pid, rows=ts.rows, cols=ts.cols)

            # Background reader: forward PTY output → WebSocket
            async def _reader():
                try:
                    while ts.is_alive:
                        output = await ts.read(4096)
                        if output:
                            await websocket.send_json({"type": "output", "data": output})
                        else:
                            await asyncio.sleep(0.05)
                except Exception:
                    pass  # WebSocket closed or PTY died

            reader_task = asyncio.create_task(_reader())

            # Main loop: read client messages
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = msg.get("type")

                if msg_type == "command":
                    data = msg.get("data", "")
                    await ts.write(data)

                elif msg_type == "resize":
                    rows = msg.get("rows", 24)
                    cols = msg.get("cols", 80)
                    ts.resize(rows, cols)

                elif msg_type == "interrupt":
                    await ts.interrupt()

                else:
                    await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

        except WebSocketDisconnect:
            logger.info("Terminal WS disconnected: %s", session_id)
        except Exception as exc:
            logger.error("Terminal WS error for %s: %s", session_id, exc, exc_info=True)
        finally:
            # Clean up reader task but keep the terminal alive for reconnection
            if "reader_task" in locals():
                reader_task.cancel()
                try:
                    await reader_task
                except asyncio.CancelledError:
                    pass

    app.include_router(sessions.router, prefix="/v1")
    return app


app = create_app()
