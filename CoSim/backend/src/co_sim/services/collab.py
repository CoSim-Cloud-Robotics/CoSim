from __future__ import annotations

import uuid
from typing import Iterable

from co_sim.core.redis import RedisLock, get_redis
from co_sim.schemas.collab import CollabDocumentCreate, CollabDocumentRead, CollabParticipant

_DOC_INDEX_KEY = "collab:documents:index"


def _doc_key(document_id: uuid.UUID | str) -> str:
    return f"collab:documents:{document_id}"


def _doc_lock_name(document_id: uuid.UUID | str) -> str:
    return f"collab:document:lock:{document_id}"


async def _save_document(document: CollabDocumentRead) -> None:
    redis = await get_redis()
    pipe = redis.pipeline()
    pipe.sadd(_DOC_INDEX_KEY, str(document.document_id))
    pipe.set(_doc_key(document.document_id), document.model_dump_json())
    await pipe.execute()


async def create_document(payload: CollabDocumentCreate) -> CollabDocumentRead:
    document = CollabDocumentRead(
        document_id=uuid.uuid4(),
        workspace_id=payload.workspace_id,
        name=payload.name,
        description=payload.description,
        template_path=payload.template_path,
        participants=[],
    )
    await _save_document(document)
    return document


async def _load_document(document_id: uuid.UUID) -> CollabDocumentRead | None:
    redis = await get_redis()
    payload = await redis.get(_doc_key(document_id))
    if not payload:
        return None
    return CollabDocumentRead.model_validate_json(payload)


async def get_document(document_id: uuid.UUID) -> CollabDocumentRead | None:
    return await _load_document(document_id)


async def get_documents(document_ids: Iterable[uuid.UUID]) -> list[CollabDocumentRead]:
    redis = await get_redis()
    pipe = redis.pipeline()
    ordered_ids = list(document_ids)
    for document_id in ordered_ids:
        pipe.get(_doc_key(document_id))
    payloads = await pipe.execute()
    documents: list[CollabDocumentRead] = []
    for payload in payloads:
        if payload:
            documents.append(CollabDocumentRead.model_validate_json(payload))
    return documents


async def add_participant(document_id: uuid.UUID, participant: CollabParticipant) -> CollabDocumentRead | None:
    lock = RedisLock(_doc_lock_name(document_id), ttl=10)
    async with lock:
        document = await _load_document(document_id)
        if not document:
            return None
        filtered = [p for p in document.participants if p.user_id != participant.user_id]
        filtered.append(participant)
        updated = document.model_copy(update={"participants": filtered})
        await _save_document(updated)
        return updated
