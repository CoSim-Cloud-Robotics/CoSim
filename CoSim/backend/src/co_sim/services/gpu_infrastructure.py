"""GPU Infrastructure - Production-grade GPU orchestration, scheduling, and isolation.

Provides:
- GPU-aware scheduler with priority queues
- Job lifecycle state machine with validation
- Coordination layer (distributed locks, pub/sub)
- Checkpointing and recovery
- Streaming/compute plane separation
- Cost/quota policy enforcement
- Observability (metrics, logs, tracing)
- Tenant/workspace isolation
"""
from __future__ import annotations

import asyncio
import enum
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from co_sim.core.redis import get_redis


# ===========================================================================
# SCHEMAS AND ENUMS
# ===========================================================================

class JobPriority(str, enum.Enum):
    """Job priority levels."""
    CRITICAL = "CRITICAL"  # Priority 0
    HIGH = "HIGH"          # Priority 1
    NORMAL = "NORMAL"      # Priority 2
    LOW = "LOW"            # Priority 3


class JobState(str, enum.Enum):
    """Job lifecycle states."""
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GPUJob(BaseModel):
    """GPU job specification."""
    job_id: str
    workspace_id: str
    gpu_requirement: int = Field(gt=0)
    memory_gb: int = Field(gt=0)
    priority: JobPriority = JobPriority.NORMAL
    max_runtime_hours: float = Field(default=24.0, gt=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InvalidStateTransition(Exception):
    """Raised when invalid state transition is attempted."""
    pass


# ===========================================================================
# GPU-AWARE SCHEDULER
# ===========================================================================

class GPUScheduler:
    """Priority-based GPU job scheduler."""

    def __init__(self):
        self._priority_map = {
            JobPriority.CRITICAL: 0,
            JobPriority.HIGH: 1,
            JobPriority.NORMAL: 2,
            JobPriority.LOW: 3,
        }

    async def submit_job(self, job: GPUJob):
        """Submit job to scheduler queue.

        Args:
            job: GPU job to schedule
        """
        redis = await get_redis()

        job_data = job.model_dump()
        job_data["submitted_at"] = time.time()
        job_data["state"] = JobState.QUEUED

        # Add to priority queue (sorted set by priority)
        priority_score = self._priority_map[job.priority]
        await redis.zadd(
            "gpu:scheduler:queue",
            {job.job_id: priority_score}
        )

        # Store job data
        await redis.set(
            f"gpu:job:{job.job_id}",
            json.dumps(job_data)
        )

    async def get_queued_jobs(self) -> List[Dict[str, Any]]:
        """Get all queued jobs in priority order.

        Returns:
            List of job dictionaries
        """
        redis = await get_redis()

        # Get job IDs from priority queue
        job_ids = await redis.zrange("gpu:scheduler:queue", 0, -1)

        jobs = []
        for job_id in job_ids:
            job_data = await redis.get(f"gpu:job:{job_id}")
            if job_data:
                jobs.append(json.loads(job_data))

        return jobs

    async def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get next job to schedule (highest priority).

        Returns:
            Job dictionary or None
        """
        redis = await get_redis()

        # Get highest priority job (lowest score)
        job_ids = await redis.zrange("gpu:scheduler:queue", 0, 0)

        if not job_ids:
            return None

        job_id = job_ids[0]
        job_data = await redis.get(f"gpu:job:{job_id}")

        if job_data:
            return json.loads(job_data)

        return None

    async def find_suitable_gpus(self, job: GPUJob) -> Optional[Dict[str, Any]]:
        """Find GPUs that meet job requirements.

        Args:
            job: GPU job with requirements

        Returns:
            GPU assignment or None
        """
        from co_sim.services.gpu_scheduling import list_available_gpus

        available_gpus = await list_available_gpus()

        # Filter by memory requirement
        suitable_gpus = [
            gpu for gpu in available_gpus
            if gpu["memory_gb"] >= job.memory_gb and gpu["status"] == "free"
        ]

        if len(suitable_gpus) < job.gpu_requirement:
            return None

        # Select N GPUs
        selected = suitable_gpus[:job.gpu_requirement]

        return {
            "gpu_ids": [gpu["gpu_id"] for gpu in selected],
            "gpus": selected,
        }


# ===========================================================================
# JOB STATE MACHINE
# ===========================================================================

class JobStateMachine:
    """Manages job lifecycle state transitions."""

    # Valid state transitions
    _TRANSITIONS = {
        JobState.PENDING: [JobState.QUEUED, JobState.CANCELLED],
        JobState.QUEUED: [JobState.SCHEDULED, JobState.CANCELLED],
        JobState.SCHEDULED: [JobState.RUNNING, JobState.FAILED, JobState.CANCELLED],
        JobState.RUNNING: [JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED],
        JobState.COMPLETED: [],
        JobState.FAILED: [JobState.QUEUED],  # Allow retry
        JobState.CANCELLED: [],
    }

    def __init__(self, job_id: str):
        self.job_id = job_id

    async def get_state(self) -> JobState:
        """Get current job state.

        Returns:
            Current JobState
        """
        redis = await get_redis()
        key = f"gpu:job:{self.job_id}:state"

        state_data = await redis.get(key)

        if state_data:
            data = json.loads(state_data)
            return JobState(data["state"])

        # Default initial state
        await self._set_state(JobState.PENDING)
        return JobState.PENDING

    async def transition(self, new_state: JobState | str, **kwargs):
        """Transition to new state.

        Args:
            new_state: Target state (JobState or string)
            **kwargs: Additional state data (e.g., error message)

        Raises:
            InvalidStateTransition: If transition is invalid
        """
        # Convert string to JobState if needed
        if isinstance(new_state, str):
            new_state = JobState(new_state)

        current_state = await self.get_state()

        # Check if transition is valid
        valid_transitions = self._TRANSITIONS.get(current_state, [])

        if new_state not in valid_transitions:
            raise InvalidStateTransition(
                f"Cannot transition from {current_state} to {new_state}"
            )

        # Perform transition
        await self._set_state(new_state, **kwargs)

    async def _set_state(self, state: JobState, **kwargs):
        """Set job state.

        Args:
            state: New state
            **kwargs: Additional state data
        """
        redis = await get_redis()
        key = f"gpu:job:{self.job_id}:state"

        state_data = {
            "state": state.value,
            "timestamp": time.time(),
            **kwargs
        }

        await redis.set(key, json.dumps(state_data))

        # Publish state change event
        await publish_job_event({
            "job_id": self.job_id,
            "event": "state_changed",
            "old_state": None,  # Could track this
            "new_state": state.value,
        })

    async def get_state_data(self) -> Dict[str, Any]:
        """Get full state data including metadata.

        Returns:
            State data dictionary
        """
        redis = await get_redis()
        key = f"gpu:job:{self.job_id}:state"

        state_data = await redis.get(key)

        if state_data:
            return json.loads(state_data)

        return {}


# ===========================================================================
# COORDINATION LAYER (Distributed Locks, Pub/Sub)
# ===========================================================================

async def acquire_lock(
    lock_key: str,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Acquire distributed lock.

    Args:
        lock_key: Lock identifier
        timeout: Lock timeout in seconds

    Returns:
        Lock info with token
    """
    redis = await get_redis()

    # Generate unique token
    token = str(uuid.uuid4())

    # Try to acquire lock with SET NX EX
    # Convert timeout to integer seconds for fakeredis compatibility
    timeout_seconds = max(1, int(timeout))

    acquired = await redis.set(
        f"lock:{lock_key}",
        token,
        nx=True,  # Only set if not exists
        ex=timeout_seconds,  # Expiration time in seconds
    )

    return {
        "acquired": bool(acquired),
        "token": token if acquired else None,
        "lock_key": lock_key,
    }


async def release_lock(lock_key: str, token: str):
    """Release distributed lock.

    Args:
        lock_key: Lock identifier
        token: Lock token from acquire
    """
    redis = await get_redis()

    # Only delete if token matches (prevent releasing someone else's lock)
    current_token = await redis.get(f"lock:{lock_key}")

    if current_token == token:
        await redis.delete(f"lock:{lock_key}")


async def publish_job_event(event: Dict[str, Any]):
    """Publish job event to pub/sub.

    Args:
        event: Event data
    """
    redis = await get_redis()

    await redis.publish(
        "gpu:job:events",
        json.dumps(event)
    )


async def subscribe_job_events(handler: Callable):
    """Subscribe to job events.

    Args:
        handler: Async function to handle events

    Returns:
        Subscription handle
    """
    redis = await get_redis()

    pubsub = redis.pubsub()
    await pubsub.subscribe("gpu:job:events")

    async def event_loop():
        async for message in pubsub.listen():
            if message["type"] == "message":
                event = json.loads(message["data"])
                await handler(event)

    # Start event loop in background
    asyncio.create_task(event_loop())

    return pubsub


# ===========================================================================
# CHECKPOINTING AND RECOVERY
# ===========================================================================

async def checkpoint_job(
    job_id: str,
    state: Dict[str, Any],
    storage_path: str = "/tmp/cosim/checkpoints",
    max_checkpoints: int = 5,
) -> str:
    """Create job checkpoint.

    Args:
        job_id: Job identifier
        state: Job state to checkpoint
        storage_path: Storage location
        max_checkpoints: Maximum checkpoints to keep

    Returns:
        Checkpoint ID
    """
    checkpoint_id = f"ckpt-{int(time.time())}"

    # Create checkpoint directory
    checkpoint_dir = Path(storage_path) / job_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Write checkpoint
    checkpoint_file = checkpoint_dir / f"{checkpoint_id}.json"
    checkpoint_file.write_text(json.dumps({
        "checkpoint_id": checkpoint_id,
        "job_id": job_id,
        "timestamp": time.time(),
        "state": state,
    }))

    # Rotate old checkpoints
    checkpoints = sorted(checkpoint_dir.glob("*.json"))
    if len(checkpoints) > max_checkpoints:
        for old_ckpt in checkpoints[:-max_checkpoints]:
            old_ckpt.unlink()

    return checkpoint_id


async def restore_from_checkpoint(
    checkpoint_id: str,
    storage_path: str = "/tmp/cosim/checkpoints",
) -> Dict[str, Any]:
    """Restore job from checkpoint.

    Args:
        checkpoint_id: Checkpoint identifier
        storage_path: Storage location

    Returns:
        Restored state
    """
    # Find checkpoint file
    for job_dir in Path(storage_path).iterdir():
        if job_dir.is_dir():
            checkpoint_file = job_dir / f"{checkpoint_id}.json"
            if checkpoint_file.exists():
                checkpoint_data = json.loads(checkpoint_file.read_text())
                return checkpoint_data["state"]

    raise FileNotFoundError(f"Checkpoint {checkpoint_id} not found")


async def list_checkpoints(
    job_id: str,
    storage_path: str = "/tmp/cosim/checkpoints",
) -> List[Dict[str, Any]]:
    """List checkpoints for job.

    Args:
        job_id: Job identifier
        storage_path: Storage location

    Returns:
        List of checkpoint metadata
    """
    checkpoint_dir = Path(storage_path) / job_id

    if not checkpoint_dir.exists():
        return []

    checkpoints = []
    for checkpoint_file in sorted(checkpoint_dir.glob("*.json")):
        data = json.loads(checkpoint_file.read_text())
        checkpoints.append(data["state"])

    return checkpoints


async def recover_job(
    job_id: str,
    storage_path: str = "/tmp/cosim/checkpoints",
) -> Dict[str, Any]:
    """Recover job from latest checkpoint.

    Args:
        job_id: Job identifier
        storage_path: Storage location

    Returns:
        Recovery info
    """
    checkpoints = await list_checkpoints(job_id, storage_path)

    if not checkpoints:
        return {
            "status": "no_checkpoint",
            "job_id": job_id,
        }

    # Get latest checkpoint
    latest_state = checkpoints[-1]

    # Re-queue job
    sm = JobStateMachine(job_id)
    await sm._set_state(JobState.QUEUED)

    return {
        "status": "recovered",
        "job_id": job_id,
        "checkpoint_state": latest_state,
        "new_state": JobState.QUEUED,
    }


# ===========================================================================
# STREAMING/COMPUTE PLANE SEPARATION
# ===========================================================================

class ComputePlane:
    """Compute plane manages job execution."""

    async def start_job(
        self,
        job_id: str,
        gpu_id: str,
    ) -> Dict[str, Any]:
        """Start job on GPU.

        Args:
            job_id: Job identifier
            gpu_id: GPU identifier

        Returns:
            Job handle
        """
        redis = await get_redis()

        job_handle = {
            "job_id": job_id,
            "gpu_id": gpu_id,
            "status": "running",
            "started_at": time.time(),
        }

        await redis.set(
            f"compute:job:{job_id}",
            json.dumps(job_handle)
        )

        return job_handle

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status.

        Args:
            job_id: Job identifier

        Returns:
            Job status
        """
        redis = await get_redis()
        data = await redis.get(f"compute:job:{job_id}")

        if data:
            return json.loads(data)

        return {"status": "not_found"}


class StreamingPlane:
    """Streaming plane manages output streaming independently."""

    async def attach_to_job(self, job_id: str) -> Dict[str, Any]:
        """Attach streaming to job.

        Args:
            job_id: Job identifier

        Returns:
            Stream info
        """
        redis = await get_redis()

        stream_info = {
            "job_id": job_id,
            "status": "streaming",
            "attached_at": time.time(),
            "buffer_size": 0,
        }

        await redis.set(
            f"streaming:job:{job_id}",
            json.dumps(stream_info)
        )

        return stream_info

    async def detach_from_job(self, job_id: str):
        """Detach streaming from job.

        Args:
            job_id: Job identifier
        """
        redis = await get_redis()
        await redis.delete(f"streaming:job:{job_id}")

    async def send_frame(self, job_id: str, frame: Any):
        """Send frame to stream.

        Args:
            job_id: Job identifier
            frame: Frame data
        """
        redis = await get_redis()

        # Add to stream buffer (using list)
        await redis.lpush(f"streaming:buffer:{job_id}", str(frame))

        # Trim buffer to prevent unbounded growth
        await redis.ltrim(f"streaming:buffer:{job_id}", 0, 99)

    async def get_metrics(self, job_id: str) -> Dict[str, Any]:
        """Get streaming metrics.

        Args:
            job_id: Job identifier

        Returns:
            Metrics dictionary
        """
        redis = await get_redis()

        buffer_size = await redis.llen(f"streaming:buffer:{job_id}")

        return {
            "job_id": job_id,
            "buffer_size": buffer_size,
            "dropped_frames": 0,  # Mock
        }


# ===========================================================================
# COST/QUOTA POLICY ENGINE
# ===========================================================================

class PolicyEngine:
    """Enforces cost and quota policies."""

    async def set_quota(
        self,
        workspace_id: str,
        max_gpu_hours_per_day: Optional[float] = None,
        max_concurrent_jobs: Optional[int] = None,
        max_spend_per_day_usd: Optional[float] = None,
        alert_threshold_pct: float = 80.0,
    ):
        """Set quota policy for workspace.

        Args:
            workspace_id: Workspace identifier
            max_gpu_hours_per_day: Max GPU hours per day
            max_concurrent_jobs: Max concurrent jobs
            max_spend_per_day_usd: Max daily spend
            alert_threshold_pct: Alert threshold percentage
        """
        redis = await get_redis()

        quota = {
            "workspace_id": workspace_id,
            "max_gpu_hours_per_day": max_gpu_hours_per_day,
            "max_concurrent_jobs": max_concurrent_jobs,
            "max_spend_per_day_usd": max_spend_per_day_usd,
            "alert_threshold_pct": alert_threshold_pct,
        }

        await redis.set(
            f"policy:quota:{workspace_id}",
            json.dumps(quota)
        )

    async def evaluate_job(self, job: GPUJob) -> Dict[str, Any]:
        """Evaluate if job is allowed under policy.

        Args:
            job: GPU job to evaluate

        Returns:
            Decision with reason
        """
        redis = await get_redis()

        # Get quota
        quota_data = await redis.get(f"policy:quota:{job.workspace_id}")

        if not quota_data:
            return {"allowed": True, "reason": "No quota set"}

        quota = json.loads(quota_data)

        # Check concurrent jobs
        if quota.get("max_concurrent_jobs"):
            active_jobs = await redis.scard(f"policy:active:{job.workspace_id}")

            if active_jobs >= quota["max_concurrent_jobs"]:
                return {
                    "allowed": False,
                    "reason": f"Max concurrent jobs ({quota['max_concurrent_jobs']}) reached"
                }

        # Mark job as active (for tracking)
        await redis.sadd(f"policy:active:{job.workspace_id}", job.job_id)

        return {"allowed": True, "reason": "Policy check passed"}

    async def track_usage(
        self,
        workspace_id: str,
        job_id: Optional[str] = None,
        gpu_hours: float = 0.0,
        cost_usd: float = 0.0,
    ):
        """Track GPU usage.

        Args:
            workspace_id: Workspace identifier
            job_id: Job identifier (optional)
            gpu_hours: GPU hours used
            cost_usd: Cost in USD
        """
        redis = await get_redis()

        usage_key = f"policy:usage:{workspace_id}"

        # Get current usage
        usage_data = await redis.get(usage_key)

        if usage_data:
            usage = json.loads(usage_data)
        else:
            usage = {"total_gpu_hours": 0.0, "total_cost_usd": 0.0}

        # Update usage
        usage["total_gpu_hours"] += gpu_hours
        usage["total_cost_usd"] += cost_usd

        await redis.set(usage_key, json.dumps(usage))

    async def get_usage(self, workspace_id: str) -> Dict[str, Any]:
        """Get workspace usage.

        Args:
            workspace_id: Workspace identifier

        Returns:
            Usage statistics
        """
        redis = await get_redis()
        usage_data = await redis.get(f"policy:usage:{workspace_id}")

        if usage_data:
            return json.loads(usage_data)

        return {"total_gpu_hours": 0.0, "total_cost_usd": 0.0}

    async def get_alerts(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Get cost/quota alerts.

        Args:
            workspace_id: Workspace identifier

        Returns:
            List of alerts
        """
        redis = await get_redis()

        quota_data = await redis.get(f"policy:quota:{workspace_id}")
        usage_data = await redis.get(f"policy:usage:{workspace_id}")

        if not quota_data or not usage_data:
            return []

        quota = json.loads(quota_data)
        usage = json.loads(usage_data)

        alerts = []

        # Check spend threshold
        if quota.get("max_spend_per_day_usd"):
            max_spend = quota["max_spend_per_day_usd"]
            current_spend = usage.get("total_cost_usd", 0.0)
            threshold_pct = quota.get("alert_threshold_pct", 80.0)

            if current_spend >= (max_spend * threshold_pct / 100.0):
                alerts.append({
                    "type": "cost_threshold",
                    "threshold_pct": threshold_pct,
                    "current_spend": current_spend,
                    "max_spend": max_spend,
                })

        return alerts


# ===========================================================================
# OBSERVABILITY LAYER
# ===========================================================================

class ObservabilityLayer:
    """Metrics, logging, and tracing."""

    async def emit_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
    ):
        """Emit metric.

        Args:
            metric_name: Metric name
            value: Metric value
            tags: Tags for filtering
        """
        redis = await get_redis()

        metric_data = {
            "metric_name": metric_name,
            "value": value,
            "timestamp": time.time(),
            "tags": tags or {},
        }

        # Store in time-series (using sorted set)
        await redis.zadd(
            f"metrics:{metric_name}",
            {json.dumps(metric_data): time.time()}
        )

        # Trim old metrics (keep last 1000)
        await redis.zremrangebyrank(f"metrics:{metric_name}", 0, -1001)

    async def query_metrics(
        self,
        metric_name: str,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Query metrics.

        Args:
            metric_name: Metric name
            tags: Filter by tags

        Returns:
            List of metrics
        """
        redis = await get_redis()

        metrics_data = await redis.zrange(
            f"metrics:{metric_name}",
            0,
            -1
        )

        metrics = []
        for data in metrics_data:
            metric = json.loads(data)

            # Filter by tags
            if tags:
                if all(metric["tags"].get(k) == v for k, v in tags.items()):
                    metrics.append(metric)
            else:
                metrics.append(metric)

        return metrics

    async def log(
        self,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Structured logging.

        Args:
            level: Log level
            message: Log message
            context: Additional context
        """
        redis = await get_redis()

        log_entry = {
            "level": level,
            "message": message,
            "timestamp": time.time(),
            "context": context or {},
        }

        await redis.lpush("logs", json.dumps(log_entry))
        await redis.ltrim("logs", 0, 9999)  # Keep last 10k logs

    async def query_logs(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query logs.

        Args:
            filters: Filter criteria
            limit: Max results

        Returns:
            List of log entries
        """
        redis = await get_redis()

        logs_data = await redis.lrange("logs", 0, limit - 1)

        logs = []
        for data in logs_data:
            log_entry = json.loads(data)

            # Filter
            if filters:
                if all(
                    log_entry["context"].get(k) == v
                    for k, v in filters.items()
                ):
                    logs.append(log_entry)
            else:
                logs.append(log_entry)

        return logs

    async def start_trace(self, job_id: str) -> str:
        """Start distributed trace.

        Args:
            job_id: Job identifier

        Returns:
            Trace ID
        """
        trace_id = f"trace-{uuid.uuid4().hex[:8]}"

        redis = await get_redis()

        trace_data = {
            "trace_id": trace_id,
            "job_id": job_id,
            "started_at": time.time(),
            "spans": [],
        }

        await redis.set(f"trace:{trace_id}", json.dumps(trace_data))

        return trace_id

    async def add_span(
        self,
        trace_id: str,
        span_name: str,
        duration_ms: float,
    ):
        """Add span to trace.

        Args:
            trace_id: Trace identifier
            span_name: Span name
            duration_ms: Duration in milliseconds
        """
        redis = await get_redis()

        trace_data = await redis.get(f"trace:{trace_id}")

        if trace_data:
            trace = json.loads(trace_data)
            trace["spans"].append({
                "name": span_name,
                "duration_ms": duration_ms,
                "timestamp": time.time(),
            })

            await redis.set(f"trace:{trace_id}", json.dumps(trace))

    async def get_trace(self, trace_id: str) -> Dict[str, Any]:
        """Get trace details.

        Args:
            trace_id: Trace identifier

        Returns:
            Trace data
        """
        redis = await get_redis()

        trace_data = await redis.get(f"trace:{trace_id}")

        if trace_data:
            trace = json.loads(trace_data)
            trace["total_duration_ms"] = sum(
                span["duration_ms"] for span in trace["spans"]
            )
            return trace

        return {}


# ===========================================================================
# TENANT/WORKSPACE ISOLATION
# ===========================================================================

class IsolationLayer:
    """Enforces tenant and workspace isolation."""

    async def allocate_resources(self, job: GPUJob):
        """Allocate resources with isolation.

        Args:
            job: GPU job
        """
        redis = await get_redis()

        # Store job in workspace namespace
        await redis.sadd(
            f"isolation:workspace:{job.workspace_id}:jobs",
            job.job_id
        )

    async def can_access_job(
        self,
        workspace_id: str,
        job_id: str,
    ) -> bool:
        """Check if workspace can access job.

        Args:
            workspace_id: Workspace identifier
            job_id: Job identifier

        Returns:
            True if access allowed
        """
        redis = await get_redis()

        # Check if job belongs to workspace
        is_member = await redis.sismember(
            f"isolation:workspace:{workspace_id}:jobs",
            job_id
        )

        return bool(is_member)

    async def get_namespace(self, workspace_id: str) -> str:
        """Get isolated namespace for workspace.

        Args:
            workspace_id: Workspace identifier

        Returns:
            Namespace string
        """
        return f"ns:{workspace_id}"

    async def set_limits(
        self,
        workspace_id: str,
        max_gpus: int,
        max_memory_gb: int,
    ):
        """Set resource limits for workspace.

        Args:
            workspace_id: Workspace identifier
            max_gpus: Max GPUs
            max_memory_gb: Max memory in GB
        """
        redis = await get_redis()

        limits = {
            "max_gpus": max_gpus,
            "max_memory_gb": max_memory_gb,
        }

        await redis.set(
            f"isolation:limits:{workspace_id}",
            json.dumps(limits)
        )

    async def get_limits(self, workspace_id: str) -> Dict[str, Any]:
        """Get resource limits for workspace.

        Args:
            workspace_id: Workspace identifier

        Returns:
            Limits dictionary
        """
        redis = await get_redis()

        limits_data = await redis.get(f"isolation:limits:{workspace_id}")

        if limits_data:
            return json.loads(limits_data)

        return {}
