from __future__ import annotations

import enum
import uuid
from typing import Dict, Optional

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from co_sim.db.base import Base
from co_sim.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WorkspaceStatus(str, enum.Enum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    PAUSED = "paused"
    HIBERNATED = "hibernated"
    DELETED = "deleted"


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[WorkspaceStatus] = mapped_column(Enum(WorkspaceStatus), default=WorkspaceStatus.PROVISIONING)
    settings: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    requested_gpu: Mapped[Optional[int]] = mapped_column(nullable=True)

    project = relationship("Project", back_populates="workspaces")
    template = relationship("Template", back_populates="workspaces")
    secrets = relationship("Secret", back_populates="workspace", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="workspace", cascade="all, delete-orphan")
    files = relationship("WorkspaceFile", back_populates="workspace", cascade="all, delete-orphan")
