from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class DebugStartRequest(BaseModel):
    language: Literal["python", "cpp"]
    file_path: Optional[str] = Field(default=None, max_length=512)
    binary_path: Optional[str] = Field(default=None, max_length=512)
    args: list[str] = Field(default_factory=list)
    adapter: Optional[Literal["gdb", "lldb"]] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)


class DebugSessionInfo(BaseModel):
    debug_id: str
    language: Literal["python", "cpp"]
    adapter: Optional[str]
    port: int
    command: list[str]
    working_dir: str


class DebugStopResponse(BaseModel):
    status: str
