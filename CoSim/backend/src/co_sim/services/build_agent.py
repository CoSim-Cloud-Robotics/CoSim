"""C++ Build Agent — compiles C++ source files and manages build artifacts.

Provides:
- BuildRequest / BuildResult schemas
- compile_cpp() — async compilation via subprocess
- execute_binary() — run compiled binaries with timeout
- persist_build_status() / get_build_status() — Redis state
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from co_sim.core.redis import get_redis


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    """Request to compile one or more C++ source files."""

    workspace_id: str
    source_files: Dict[str, str] = Field(
        ..., description="Mapping of filename -> source code content"
    )
    compiler: str = Field(default="g++", pattern=r"^(g\+\+|clang\+\+)$")
    flags: List[str] = Field(default_factory=lambda: ["-std=c++17", "-Wall"])
    output_name: str = Field(default="a.out")
    generate_compile_commands: bool = Field(default=False)


class BuildResult(BaseModel):
    """Result of a C++ compilation."""

    status: str  # "success" | "error"
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    artifact_path: Optional[str] = None
    compile_commands: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Core compilation
# ---------------------------------------------------------------------------

async def compile_cpp(
    request: BuildRequest,
    build_root: str = "/tmp/cosim/builds",
) -> BuildResult:
    """Compile C++ source files into an executable.

    1. Write source files to a build directory.
    2. Invoke the compiler subprocess.
    3. Optionally generate compile_commands.json.
    4. Return the result.
    """
    build_dir = Path(build_root) / request.workspace_id / str(uuid.uuid4())[:8]
    build_dir.mkdir(parents=True, exist_ok=True)

    # Write source files to disk
    source_paths: List[Path] = []
    for filename, content in request.source_files.items():
        file_path = build_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        # Only compile .cpp/.c files, not headers
        if filename.endswith((".cpp", ".c", ".cc", ".cxx")):
            source_paths.append(file_path)

    if not source_paths:
        return BuildResult(
            status="error",
            exit_code=1,
            stderr="No compilable source files found (.cpp, .c, .cc, .cxx)",
        )

    output_path = build_dir / request.output_name

    # Build the compiler command
    cmd = [
        request.compiler,
        *request.flags,
        # Include the build dir so relative #includes work
        f"-I{build_dir}",
        *[str(p) for p in source_paths],
        "-o",
        str(output_path),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(build_dir),
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=60.0
        )
    except asyncio.TimeoutError:
        return BuildResult(
            status="error",
            exit_code=-1,
            stderr="Compilation timed out (60s limit)",
        )
    except FileNotFoundError:
        return BuildResult(
            status="error",
            exit_code=-1,
            stderr=f"Compiler not found: {request.compiler}",
        )

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    exit_code = process.returncode or 0

    compile_commands = None
    if request.generate_compile_commands and exit_code == 0:
        compile_commands = [
            {
                "directory": str(build_dir),
                "command": " ".join(cmd),
                "file": str(p),
            }
            for p in source_paths
        ]

    if exit_code == 0:
        return BuildResult(
            status="success",
            exit_code=0,
            stdout=stdout_text,
            stderr=stderr_text,
            artifact_path=str(output_path),
            compile_commands=compile_commands,
        )
    else:
        return BuildResult(
            status="error",
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
        )


# ---------------------------------------------------------------------------
# Binary execution
# ---------------------------------------------------------------------------

async def execute_binary(
    binary_path: str,
    args: List[str] | None = None,
    stdin_data: str | None = None,
    timeout: int = 30,
    cwd: str | None = None,
) -> Dict[str, Any]:
    """Execute a compiled binary and capture output."""
    if not os.path.isfile(binary_path):
        return {"exit_code": -1, "stdout": "", "stderr": f"Binary not found: {binary_path}"}

    cmd = [binary_path, *(args or [])]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
            cwd=cwd,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(input=stdin_data.encode() if stdin_data else None),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return {"exit_code": -1, "stdout": "", "stderr": f"Execution timed out ({timeout}s)"}

    return {
        "exit_code": process.returncode or 0,
        "stdout": stdout_bytes.decode("utf-8", errors="replace"),
        "stderr": stderr_bytes.decode("utf-8", errors="replace"),
    }


# ---------------------------------------------------------------------------
# Redis state management
# ---------------------------------------------------------------------------

_BUILD_KEY_PREFIX = "cosim:build"


def _build_key(workspace_id: str, build_id: str) -> str:
    return f"{_BUILD_KEY_PREFIX}:{workspace_id}:{build_id}"


async def persist_build_status(
    workspace_id: str,
    build_id: str,
    *,
    status: str,
    artifact: str | None = None,
    ttl: int = 3600,
) -> None:
    """Store build status in Redis."""
    redis = await get_redis()
    data = {"status": status}
    if artifact:
        data["artifact"] = artifact
    await redis.hset(_build_key(workspace_id, build_id), mapping=data)
    await redis.expire(_build_key(workspace_id, build_id), ttl)


async def get_build_status(workspace_id: str, build_id: str) -> Dict[str, str] | None:
    """Retrieve build status from Redis."""
    redis = await get_redis()
    data = await redis.hgetall(_build_key(workspace_id, build_id))
    return data if data else None
