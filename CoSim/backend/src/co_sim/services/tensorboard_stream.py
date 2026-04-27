"""TensorBoard streaming service.

Bridges the RL training agent's Redis-backed metric stream into a
TensorBoard-compatible logdir and supervises the ``tensorboard`` subprocess
that exposes those logs to the workspace.

Layout
------
- ``<root>/<workspace_id>/<run_id>/metrics.jsonl`` — append-only metric log,
  always written so the UI can render a sparkline even when ``tensorboardX``
  isn't installed.
- ``<root>/<workspace_id>/<run_id>/events.out.tfevents.*`` — written via
  ``tensorboardX`` when available (best-effort, never blocking).
- Redis keys ``cosim:tb:stream:<workspace_id>:<run_id>`` track running
  TensorBoard processes (port, pid, status). The set
  ``cosim:tb:streams:<workspace_id>`` indexes them per workspace.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from co_sim.core.redis import get_redis
from co_sim.services import rl_training_agent

DEFAULT_LOG_ROOT = Path(os.environ.get("COSIM_TB_ROOT", "/tmp/cosim/tb-logs"))
_STREAM_KEY_PREFIX = "cosim:tb:stream"
_WORKSPACE_INDEX_PREFIX = "cosim:tb:streams"
_DEFAULT_TTL_SECONDS = 60 * 60 * 24


def _stream_key(workspace_id: str, run_id: str) -> str:
    return f"{_STREAM_KEY_PREFIX}:{workspace_id}:{run_id}"


def _workspace_index_key(workspace_id: str) -> str:
    return f"{_WORKSPACE_INDEX_PREFIX}:{workspace_id}"


def _safe_segment(value: str, *, label: str) -> str:
    """Reject path segments that try to escape the logs root."""

    if not value or value in {".", ".."} or "/" in value or "\\" in value or ".." in Path(value).parts:
        raise ValueError(f"invalid {label}: {value!r}")
    return value


def resolve_logdir(*, workspace_id: str, run_id: str, root: Path = DEFAULT_LOG_ROOT) -> Path:
    """Return the per-run logdir, creating it on demand."""

    safe_workspace = _safe_segment(workspace_id, label="workspace_id")
    safe_run = _safe_segment(run_id, label="run_id")
    return Path(root) / safe_workspace / safe_run


# ---------------------------------------------------------------------------
# Metric writing
# ---------------------------------------------------------------------------


async def write_metrics(
    *,
    workspace_id: str,
    run_id: str,
    timestep: int,
    scalars: dict[str, float],
    root: Path = DEFAULT_LOG_ROOT,
) -> Path:
    """Append a metrics row to the per-run JSONL file (and TF events if avail)."""

    logdir = resolve_logdir(workspace_id=workspace_id, run_id=run_id, root=root)
    await asyncio.to_thread(logdir.mkdir, parents=True, exist_ok=True)

    payload = {"timestep": int(timestep), "scalars": dict(scalars), "wall_time": time.time()}
    jsonl_path = logdir / "metrics.jsonl"

    def _append() -> None:
        with jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")

    await asyncio.to_thread(_append)

    # Best-effort TensorBoard event writing — never block on import errors.
    try:  # pragma: no cover - optional dependency
        from tensorboardX import SummaryWriter  # type: ignore

        def _write_events() -> None:
            writer = SummaryWriter(logdir=str(logdir))
            try:
                for name, value in scalars.items():
                    writer.add_scalar(name, float(value), int(timestep))
            finally:
                writer.flush()
                writer.close()

        await asyncio.to_thread(_write_events)
    except Exception:  # pragma: no cover - tensorboardX optional
        pass

    return jsonl_path


# ---------------------------------------------------------------------------
# Stream supervision (tensorboard subprocess)
# ---------------------------------------------------------------------------


@dataclass
class TensorBoardStreamInfo:
    workspace_id: str
    run_id: str
    port: int
    pid: int
    logdir: str
    status: str = "running"
    started_at: float = 0.0


async def _default_spawner(*, logdir: Path, port: int):  # pragma: no cover - real spawn
    binary = shutil.which("tensorboard") or "tensorboard"
    return await asyncio.create_subprocess_exec(
        binary,
        "--logdir",
        str(logdir),
        "--port",
        str(port),
        "--host",
        "0.0.0.0",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


_PROCESSES: dict[str, Any] = {}


async def start_stream(
    *,
    workspace_id: str,
    run_id: str,
    port: int,
    root: Path = DEFAULT_LOG_ROOT,
    spawner: Optional[Callable[..., Awaitable[Any]]] = None,
) -> TensorBoardStreamInfo:
    """Launch a TensorBoard subprocess and persist its descriptor in Redis."""

    logdir = resolve_logdir(workspace_id=workspace_id, run_id=run_id, root=root)
    await asyncio.to_thread(logdir.mkdir, parents=True, exist_ok=True)

    spawn = spawner or _default_spawner
    process = await spawn(logdir=logdir, port=port)
    pid = int(getattr(process, "pid", 0) or 0)

    info = TensorBoardStreamInfo(
        workspace_id=workspace_id,
        run_id=run_id,
        port=port,
        pid=pid,
        logdir=str(logdir),
        started_at=time.time(),
    )
    _PROCESSES[_stream_key(workspace_id, run_id)] = process

    redis = await get_redis()
    pipe = redis.pipeline()
    pipe.hset(
        _stream_key(workspace_id, run_id),
        mapping={
            "workspace_id": workspace_id,
            "run_id": run_id,
            "port": str(port),
            "pid": str(pid),
            "logdir": info.logdir,
            "status": info.status,
            "started_at": str(info.started_at),
        },
    )
    pipe.expire(_stream_key(workspace_id, run_id), _DEFAULT_TTL_SECONDS)
    pipe.sadd(_workspace_index_key(workspace_id), run_id)
    pipe.expire(_workspace_index_key(workspace_id), _DEFAULT_TTL_SECONDS)
    await pipe.execute()
    return info


async def stop_stream(*, workspace_id: str, run_id: str) -> bool:
    """Terminate the TensorBoard subprocess and clear Redis state."""

    redis = await get_redis()
    state = await redis.hgetall(_stream_key(workspace_id, run_id))
    if not state:
        _PROCESSES.pop(_stream_key(workspace_id, run_id), None)
        return False

    process = _PROCESSES.pop(_stream_key(workspace_id, run_id), None)
    if process is not None:
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:  # pragma: no cover - rarely hit in tests
            process.kill()
            await process.wait()
        except ProcessLookupError:  # pragma: no cover - already gone
            pass

    pipe = redis.pipeline()
    pipe.delete(_stream_key(workspace_id, run_id))
    pipe.srem(_workspace_index_key(workspace_id), run_id)
    await pipe.execute()
    return True


async def get_stream_state(*, workspace_id: str, run_id: str) -> Optional[dict[str, str]]:
    redis = await get_redis()
    data = await redis.hgetall(_stream_key(workspace_id, run_id))
    return data if data else None


async def list_active_streams(*, workspace_id: str) -> list[dict[str, str]]:
    """Return all active TensorBoard streams for a workspace."""

    redis = await get_redis()
    run_ids = await redis.smembers(_workspace_index_key(workspace_id))
    if not run_ids:
        return []
    streams: list[dict[str, str]] = []
    for run_id in sorted(run_ids):
        data = await redis.hgetall(_stream_key(workspace_id, run_id))
        if data:
            streams.append(data)
    return streams


# ---------------------------------------------------------------------------
# Drain RL training history
# ---------------------------------------------------------------------------


async def drain_training_history(
    *, workspace_id: str, run_id: str, root: Path = DEFAULT_LOG_ROOT
) -> int:
    """Hydrate a logdir from RL training metrics already stored in Redis.

    Returns the number of metric rows written.
    """

    redis = await get_redis()
    history_key = f"rl_training:{run_id}:history"
    raw_entries = await redis.zrange(history_key, 0, -1)
    if not raw_entries:
        return 0

    count = 0
    for raw in raw_entries:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue

        scalars: dict[str, float] = {}
        for key in ("mean_reward", "episode", "episode_length"):
            if key in entry and entry[key] is not None:
                try:
                    scalars[key] = float(entry[key])
                except (TypeError, ValueError):
                    continue
        if not scalars:
            continue

        await write_metrics(
            workspace_id=workspace_id,
            run_id=run_id,
            timestep=int(entry.get("timestep", 0)),
            scalars=scalars,
            root=root,
        )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Bridge helper used by RL training agent
# ---------------------------------------------------------------------------


async def mirror_training_metric(
    *,
    workspace_id: str,
    run_id: str,
    timestep: int,
    mean_reward: float,
    episode: int,
    episode_length: Optional[int] = None,
    root: Path = DEFAULT_LOG_ROOT,
) -> None:
    """Convenience wrapper used to forward a single training tick into the logdir.

    Intentionally tolerant: any error is swallowed so the training agent's
    main loop is never blocked on metric forwarding.
    """

    scalars: dict[str, float] = {"mean_reward": float(mean_reward), "episode": float(episode)}
    if episode_length is not None:
        scalars["episode_length"] = float(episode_length)
    try:
        await write_metrics(
            workspace_id=workspace_id,
            run_id=run_id,
            timestep=timestep,
            scalars=scalars,
            root=root,
        )
    except Exception:  # pragma: no cover - never propagate
        pass


# Re-export the agent reference so callers can stay decoupled.
__all__ = [
    "DEFAULT_LOG_ROOT",
    "TensorBoardStreamInfo",
    "drain_training_history",
    "get_stream_state",
    "list_active_streams",
    "mirror_training_metric",
    "resolve_logdir",
    "rl_training_agent",
    "start_stream",
    "stop_stream",
    "write_metrics",
]
