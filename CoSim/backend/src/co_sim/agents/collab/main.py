from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from co_sim.api.v1.routes import collab
from co_sim.core import logging as logging_config
from co_sim.core.redis import close_redis, init_redis
from co_sim.services import session_events


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging_config.configure_logging()
    await init_redis()
    await session_events.start_listener()
    try:
        yield
    finally:
        await session_events.stop_listener()
        await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(title="CoSim Collaboration Service", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": "collab-agent"}

    app.include_router(collab.router, prefix="/v1")
    return app


app = create_app()
