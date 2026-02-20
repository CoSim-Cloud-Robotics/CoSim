from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GitStatusEntry(BaseModel):
    path: str
    staged: str = Field(min_length=1, max_length=1)
    unstaged: str = Field(min_length=1, max_length=1)


class GitStatusResponse(BaseModel):
    entries: list[GitStatusEntry]


class GitAddRequest(BaseModel):
    paths: Optional[list[str]] = None


class GitCommitRequest(BaseModel):
    message: str = Field(min_length=1)


class GitDiffResponse(BaseModel):
    diff: str
