from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from co_sim.core.config import settings
from co_sim.core import redis as redis_helpers
from co_sim.db.base import Base
from co_sim.models.organization import Organization
from co_sim.models.project import Project
from co_sim.models.session import Session as SessionModel, SessionStatus
from co_sim.models.workspace import Workspace
from co_sim.schemas.session import SessionCreate
from co_sim.services import session_events, sessions as session_service


async def _wait_for_event(events: list[dict], event_type: str, session_id: str, timeout: float = 2.0) -> dict:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        for event in events:
            if event.get("type") != event_type:
                continue
            if event.get("session", {}).get("id") == session_id:
                return event
        await asyncio.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {event_type} for session {session_id}")


@pytest.mark.asyncio
async def test_session_events_with_real_services() -> None:
    database_uri = os.getenv("COSIM_INTEGRATION_DATABASE_URI")
    redis_url = os.getenv("COSIM_INTEGRATION_REDIS_URL")
    if not database_uri or not redis_url:
        pytest.skip("COSIM_INTEGRATION_DATABASE_URI and COSIM_INTEGRATION_REDIS_URL are required")

    settings.redis_url = redis_url
    await redis_helpers.reset_redis_state()
    redis = await redis_helpers.init_redis(force=True)
    await redis.flushdb()

    sync_uri = database_uri.replace("+asyncpg", "+psycopg") if "+asyncpg" in database_uri else database_uri
    sync_engine = create_engine(sync_uri, future=True)
    Base.metadata.create_all(bind=sync_engine)

    async_engine = create_async_engine(database_uri, future=True)
    async_session = async_sessionmaker(bind=async_engine, expire_on_commit=False, autoflush=False)

    events: list[dict] = []

    async def _handler(event: dict) -> None:
        events.append(event)

    session_events.register_handler("integration", _handler)
    await session_events.start_listener()

    created_id: str | None = None
    org_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None

    try:
        async with async_session() as db_session:
            org = Organization(
                name="Integration Org",
                slug=f"org-{uuid.uuid4().hex[:8]}",
            )
            db_session.add(org)
            await db_session.flush()
            org_id = org.id

            project = Project(
                organization_id=org.id,
                name="Integration Project",
                slug=f"proj-{uuid.uuid4().hex[:8]}",
            )
            db_session.add(project)
            await db_session.flush()
            project_id = project.id

            workspace = Workspace(
                project_id=project.id,
                name="Integration Workspace",
                slug=f"ws-{uuid.uuid4().hex[:8]}",
            )
            db_session.add(workspace)
            await db_session.commit()
            await db_session.refresh(workspace)
            workspace_id = workspace.id

            created = await session_service.create_session(
                db_session,
                SessionCreate(workspace_id=workspace.id),
            )
            created_id = str(created.id)
            await _wait_for_event(events, "session.created", created_id)

            db_session_obj = await session_service.get_session(db_session, created.id)
            assert db_session_obj is not None

            updated = await session_service.transition_status(db_session, db_session_obj, SessionStatus.RUNNING)
            await _wait_for_event(events, "session.updated", str(updated.id))

            await db_session.execute(delete(SessionModel).where(SessionModel.id == updated.id))
            await db_session.commit()
            await db_session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            await db_session.execute(delete(Project).where(Project.id == project_id))
            await db_session.execute(delete(Organization).where(Organization.id == org_id))
            await db_session.commit()
    finally:
        session_events.unregister_handler("integration")
        await session_events.stop_listener()
        await redis_helpers.reset_redis_state()
        await async_engine.dispose()
        sync_engine.dispose()
