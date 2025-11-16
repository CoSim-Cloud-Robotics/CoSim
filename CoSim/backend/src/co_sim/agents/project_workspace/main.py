from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from co_sim.api.v1.routes import datasets, organizations, projects, secrets, templates, workspaces
from co_sim.core import logging as logging_config
from co_sim.core.redis import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging_config.configure_logging()
    await init_redis()
    try:
        yield
    finally:
        await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(title="CoSim Project & Workspace Agent", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": "project-agent"}

    for router in (
        organizations.router,
        projects.router,
        workspaces.router,
        datasets.router,
        templates.router,
        secrets.router,
    ):
        app.include_router(router, prefix="/v1")

    return app


app = create_app()
