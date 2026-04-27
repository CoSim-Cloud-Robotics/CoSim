from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class DebugStartRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=512)
    args: list[str] = Field(default_factory=list)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    # Reserved for future runtimes; only "python" is currently supported.
    language: Literal["python"] = "python"


class DebugSessionInfo(BaseModel):
    debug_id: str
    language: Literal["python"] = "python"
    port: int
    command: list[str]
    working_dir: str


class DebugStopResponse(BaseModel):
    status: str
