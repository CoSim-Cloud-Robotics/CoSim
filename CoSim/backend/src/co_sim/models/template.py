from __future__ import annotations

import enum
import uuid
from typing import Dict, Optional

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from co_sim.db.base import Base
from co_sim.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TemplateKind(str, enum.Enum):
    RL_MUJOCO = "rl_mujoco"
    RL_PYBULLET = "rl_pybullet"
    SLAM = "slam"
    EMPTY = "empty"


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "templates"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[TemplateKind] = mapped_column(Enum(TemplateKind), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    config: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)

    default_for_org_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    projects = relationship("Project", back_populates="template")
    workspaces = relationship("Workspace", back_populates="template")
