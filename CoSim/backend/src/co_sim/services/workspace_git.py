from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.services import workspace_fs


@dataclass
class GitStatusEntry:
    path: str
    staged: str
    unstaged: str


async def _run_git(root: Path, args: Iterable[str]) -> str:
    def _run() -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(stderr or f"git {' '.join(args)} failed")
        return completed.stdout

    return await asyncio.to_thread(_run)


async def ensure_repo(session: AsyncSession, workspace_id: UUID | str) -> Path:
    await workspace_fs.sync_from_db(session, workspace_id)
    root = await workspace_fs.ensure_workspace_dir(workspace_id)
    git_dir = root / ".git"
    if not git_dir.exists():
        await _run_git(root, ["init"])
        await _run_git(root, ["config", "user.name", "CoSim"])
        await _run_git(root, ["config", "user.email", "cosim@local"])
    return root


def _parse_status(output: str) -> list[GitStatusEntry]:
    entries: list[GitStatusEntry] = []
    for line in output.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        entries.append(GitStatusEntry(path=path, staged=status[0], unstaged=status[1]))
    return entries


async def git_status(session: AsyncSession, workspace_id: UUID | str) -> list[GitStatusEntry]:
    root = await ensure_repo(session, workspace_id)
    output = await _run_git(root, ["status", "--porcelain"])
    return _parse_status(output)


async def git_add(session: AsyncSession, workspace_id: UUID | str, paths: list[str] | None = None) -> None:
    root = await ensure_repo(session, workspace_id)
    if paths:
        await _run_git(root, ["add", "--", *paths])
    else:
        await _run_git(root, ["add", "-A"])


async def git_commit(session: AsyncSession, workspace_id: UUID | str, message: str) -> str:
    root = await ensure_repo(session, workspace_id)
    output = await _run_git(root, ["commit", "-m", message])
    return output


async def git_diff(
    session: AsyncSession,
    workspace_id: UUID | str,
    *,
    staged: bool = False,
    path: str | None = None,
) -> str:
    root = await ensure_repo(session, workspace_id)
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        args.extend(["--", path])
    return await _run_git(root, args)
