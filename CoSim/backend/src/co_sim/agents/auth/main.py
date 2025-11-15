from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from co_sim.api.v1.routes import auth as auth_routes
from co_sim.api.v1.routes import users as user_routes
from co_sim.core import logging as logging_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging_config.configure_logging()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="CoSim Auth Agent", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": "auth-agent"}

    app.include_router(auth_routes.router, prefix="/v1")
    app.include_router(user_routes.router, prefix="/v1")
    return app


app = create_app()
