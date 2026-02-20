from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from co_sim.schemas.base import TimestampedModel


class WorkspaceFileUpsert(BaseModel):
    path: str = Field(max_length=512)
    content: str
    language: Optional[str] = Field(default=None, max_length=32)


class WorkspaceFileRead(TimestampedModel):
    workspace_id: UUID
    path: str
    content: str
    language: Optional[str]


class WorkspaceFileRename(BaseModel):
    source_path: str = Field(max_length=512)
    destination_path: str = Field(max_length=512)
