from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from co_sim.db.base import Base
from co_sim.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WorkspaceFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_files"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    workspace = relationship("Workspace", back_populates="files")

    __table_args__ = (UniqueConstraint("workspace_id", "path", name="uq_workspace_file_path"),)
