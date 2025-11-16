from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from co_sim.db.base import Base
from co_sim.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SessionType(str, enum.Enum):
    IDE = "ide"
    SIMULATOR = "simulator"


class SessionStatus(str, enum.Enum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    TERMINATING = "terminating"
    TERMINATED = "terminated"


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    session_type: Mapped[SessionType] = mapped_column(
        Enum(SessionType, native_enum=False), nullable=False
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, native_enum=False), nullable=False, default=SessionStatus.PENDING
    )
    requested_gpu: Mapped[Optional[int]] = mapped_column(nullable=True)
    details: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace = relationship("Workspace", back_populates="sessions")
    participants = relationship("SessionParticipant", back_populates="session", cascade="all, delete-orphan")


class SessionParticipant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "session_participants"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), default="editor")

    session = relationship("Session", back_populates="participants")
    user = relationship("User")
