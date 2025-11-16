from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from co_sim.core import redis as redis_helpers
from co_sim.schemas.collab import CollabDocumentCreate, CollabParticipant
from co_sim.services import collab


@pytest_asyncio.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


@pytest.mark.asyncio
async def test_create_and_fetch_document():
    payload = CollabDocumentCreate(
        workspace_id=uuid.uuid4(),
        name="Test Doc",
        description="desc",
        template_path="template.md",
    )

    created = await collab.create_document(payload)
    fetched = await collab.get_document(created.document_id)

    assert fetched is not None
    assert fetched.document_id == created.document_id
    assert fetched.participants == []


@pytest.mark.asyncio
async def test_add_participant_replaces_existing():
    payload = CollabDocumentCreate(
        workspace_id=uuid.uuid4(),
        name="Doc",
    )
    document = await collab.create_document(payload)

    user_id = uuid.uuid4()
    await collab.add_participant(
        document.document_id,
        CollabParticipant(user_id=user_id, role="viewer"),
    )

    updated = await collab.add_participant(
        document.document_id,
        CollabParticipant(user_id=user_id, role="editor"),
    )

    assert updated is not None
    assert len(updated.participants) == 1
    assert updated.participants[0].role == "editor"
