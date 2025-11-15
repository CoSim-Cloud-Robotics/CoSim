from __future__ import annotations

from fastapi import APIRouter

from co_sim.api.v1.routes import (
    auth,
    collab,
    datasets,
    organizations,
    projects,
    secrets,
    sessions,
    templates,
    users,
    workspaces,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(workspaces.router)
api_router.include_router(datasets.router)
api_router.include_router(templates.router)
api_router.include_router(secrets.router)
api_router.include_router(sessions.router)
api_router.include_router(collab.router)
api_router.include_router(users.router)
