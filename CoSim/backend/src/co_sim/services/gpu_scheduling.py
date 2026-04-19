"""GPU Scheduling Agent — resource allocation, cost tracking, and guard policies.

Provides:
- GPUResourceRequest / GPUAllocation / CostGuardPolicy schemas
- check_gpu_availability() / list_available_gpus() — GPU discovery
- allocate_gpu() / release_gpu() — GPU resource management
- set_cost_guard_policy() / check_cost_guard_limits() — spending controls
- track_gpu_cost() / get_workspace_gpu_spend() — cost tracking
- monitor_gpu_allocation() — usage monitoring
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from co_sim.core.redis import get_redis


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GPUResourceRequest(BaseModel):
    """Request for GPU resources."""

    workspace_id: str
    task_id: str
    gpu_count: int = Field(gt=0)
    gpu_memory_gb: int = Field(gt=0)
    max_duration_hours: float = Field(default=24.0, gt=0)


class GPUAllocation(BaseModel):
    """Allocated GPU resources."""

    allocation_id: str
    workspace_id: str
    task_id: str
    gpu_ids: List[str]
    gpu_memory_allocated_gb: int
    status: str  # pending, running, completed, failed, terminated
    allocated_at: float = Field(default_factory=time.time)


class CostGuardPolicy(BaseModel):
    """Cost guard policy for GPU spending limits."""

    workspace_id: str
    max_concurrent_gpus: int = Field(gt=0)
    max_spend_per_day_usd: float = Field(gt=0)
    max_spend_per_task_usd: float = Field(default=0.0, ge=0)
    alert_threshold_usd: float = Field(default=0.0, ge=0)


# ---------------------------------------------------------------------------
# GPU Availability and Discovery
# ---------------------------------------------------------------------------

async def check_gpu_availability(
    gpu_count: int,
    gpu_memory_gb: int,
) -> bool:
    """Check if requested GPU resources are available.

    Args:
        gpu_count: Number of GPUs requested
        gpu_memory_gb: Memory per GPU in GB

    Returns:
        True if resources are available
    """
    available_gpus = await list_available_gpus()

    # Filter GPUs that meet memory requirements and are free
    suitable_gpus = [
        gpu for gpu in available_gpus
        if gpu["memory_gb"] >= gpu_memory_gb and gpu["status"] == "free"
    ]

    return len(suitable_gpus) >= gpu_count


async def list_available_gpus() -> List[Dict[str, Any]]:
    """List all available GPUs in the cluster.

    Returns:
        List of GPU metadata dictionaries
    """
    # Mock implementation - in production, this would query actual GPU nodes
    # For testing, return a set of mock GPUs
    return [
        {"gpu_id": "gpu-0", "memory_gb": 16, "status": "free", "node": "node-1"},
        {"gpu_id": "gpu-1", "memory_gb": 16, "status": "free", "node": "node-1"},
        {"gpu_id": "gpu-2", "memory_gb": 32, "status": "free", "node": "node-2"},
        {"gpu_id": "gpu-3", "memory_gb": 32, "status": "free", "node": "node-2"},
    ]


# ---------------------------------------------------------------------------
# GPU Allocation and Release
# ---------------------------------------------------------------------------

async def allocate_gpu(request: GPUResourceRequest) -> GPUAllocation:
    """Allocate GPU resources for a task.

    Args:
        request: GPU resource request

    Returns:
        GPUAllocation with allocated resources
    """
    available_gpus = await list_available_gpus()

    # Find suitable GPUs
    suitable_gpus = [
        gpu for gpu in available_gpus
        if gpu["memory_gb"] >= request.gpu_memory_gb and gpu["status"] == "free"
    ]

    if len(suitable_gpus) < request.gpu_count:
        raise RuntimeError(f"Insufficient GPU resources available")

    # Allocate the first N suitable GPUs
    allocated_gpu_ids = [gpu["gpu_id"] for gpu in suitable_gpus[:request.gpu_count]]

    allocation = GPUAllocation(
        allocation_id=f"alloc-{uuid.uuid4().hex[:8]}",
        workspace_id=request.workspace_id,
        task_id=request.task_id,
        gpu_ids=allocated_gpu_ids,
        gpu_memory_allocated_gb=request.gpu_memory_gb,
        status="running",
    )

    # Persist allocation state
    await _persist_allocation(allocation, request.max_duration_hours)

    return allocation


async def release_gpu(allocation_id: str) -> Dict[str, Any]:
    """Release GPU resources.

    Args:
        allocation_id: Allocation identifier

    Returns:
        Release status
    """
    redis = await get_redis()
    key = f"gpu_allocation:{allocation_id}"

    # Get allocation
    data = await redis.get(key)
    if data is None:
        raise ValueError(f"Allocation {allocation_id} not found")

    allocation_data = json.loads(data)
    allocation_data["status"] = "completed"

    # Update status
    await redis.set(key, json.dumps(allocation_data))

    # Remove from active allocations
    workspace_id = allocation_data["workspace_id"]
    await redis.srem(f"gpu_allocations:{workspace_id}", allocation_id)

    return {
        "status": "released",
        "allocation_id": allocation_id,
    }


# ---------------------------------------------------------------------------
# Cost Guard Policies
# ---------------------------------------------------------------------------

async def set_cost_guard_policy(policy: CostGuardPolicy):
    """Set cost guard policy for a workspace.

    Args:
        policy: Cost guard policy configuration
    """
    redis = await get_redis()
    key = f"cost_guard_policy:{policy.workspace_id}"

    await redis.set(key, json.dumps(policy.model_dump()))


async def get_cost_guard_policy(workspace_id: str) -> Optional[Dict[str, Any]]:
    """Get cost guard policy for a workspace.

    Args:
        workspace_id: Workspace identifier

    Returns:
        Cost guard policy dictionary, or None if not set
    """
    redis = await get_redis()
    key = f"cost_guard_policy:{workspace_id}"

    data = await redis.get(key)
    if data is None:
        return None

    return json.loads(data)


async def check_cost_guard_limits(
    request: GPUResourceRequest,
) -> Tuple[bool, str]:
    """Check if request violates cost guard limits.

    Args:
        request: GPU resource request

    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    policy = await get_cost_guard_policy(request.workspace_id)

    if policy is None:
        # No policy set, allow by default
        return True, "No cost guard policy set"

    # Check concurrent GPU limit
    active_allocations = await list_workspace_allocations(request.workspace_id)
    active_gpu_count = sum(
        len(alloc.get("gpu_ids", []))
        for alloc in active_allocations
        if alloc.get("status") == "running"
    )

    if active_gpu_count + request.gpu_count > policy["max_concurrent_gpus"]:
        return False, f"Would exceed concurrent GPU limit ({policy['max_concurrent_gpus']})"

    # Check daily spend limit
    spend = await get_workspace_gpu_spend(request.workspace_id)
    if spend["total_cost_usd"] >= policy["max_spend_per_day_usd"]:
        return False, f"Daily spend limit reached (${policy['max_spend_per_day_usd']})"

    return True, "Request allowed"


# ---------------------------------------------------------------------------
# Cost Tracking
# ---------------------------------------------------------------------------

async def track_gpu_cost(
    workspace_id: str,
    allocation_id: str,
    gpu_hours: float,
    cost_usd: float,
):
    """Track GPU usage cost for billing.

    Args:
        workspace_id: Workspace identifier
        allocation_id: Allocation identifier
        gpu_hours: GPU hours used
        cost_usd: Cost in USD
    """
    redis = await get_redis()

    # Store cost record
    cost_record = {
        "allocation_id": allocation_id,
        "gpu_hours": gpu_hours,
        "cost_usd": cost_usd,
        "timestamp": time.time(),
    }

    key = f"gpu_costs:{workspace_id}"
    await redis.lpush(key, json.dumps(cost_record))

    # Keep only last 1000 records
    await redis.ltrim(key, 0, 999)


async def get_workspace_gpu_spend(workspace_id: str) -> Dict[str, Any]:
    """Get total GPU spend for a workspace.

    Args:
        workspace_id: Workspace identifier

    Returns:
        Dictionary with spend statistics
    """
    redis = await get_redis()
    key = f"gpu_costs:{workspace_id}"

    # Get all cost records
    records = await redis.lrange(key, 0, -1)

    total_cost = 0.0
    total_hours = 0.0

    for record_json in records:
        record = json.loads(record_json)
        total_cost += record["cost_usd"]
        total_hours += record["gpu_hours"]

    return {
        "workspace_id": workspace_id,
        "total_cost_usd": total_cost,
        "total_gpu_hours": total_hours,
        "num_allocations": len(records),
    }


# ---------------------------------------------------------------------------
# Monitoring and Timeouts
# ---------------------------------------------------------------------------

async def monitor_gpu_allocation(allocation_id: str) -> Dict[str, Any]:
    """Monitor GPU allocation status and usage.

    Args:
        allocation_id: Allocation identifier

    Returns:
        Allocation status and metrics
    """
    state = await get_allocation_state(allocation_id)

    if state is None:
        raise ValueError(f"Allocation {allocation_id} not found")

    # Mock GPU utilization - in production, query actual GPU metrics
    return {
        "allocation_id": allocation_id,
        "status": state["status"],
        "gpu_ids": state["gpu_ids"],
        "gpu_utilization": [85.0] * len(state["gpu_ids"]),  # Mock: 85% utilization
        "memory_used_gb": [state["gpu_memory_allocated_gb"] * 0.8] * len(state["gpu_ids"]),
    }


async def check_allocation_timeout(allocation_id: str) -> bool:
    """Check if allocation has exceeded max duration.

    Args:
        allocation_id: Allocation identifier

    Returns:
        True if allocation has timed out
    """
    state = await get_allocation_state(allocation_id)

    if state is None:
        return False

    allocated_at = state.get("allocated_at", 0)
    max_duration_seconds = state.get("max_duration_hours", 24.0) * 3600

    elapsed = time.time() - allocated_at
    return elapsed > max_duration_seconds


# ---------------------------------------------------------------------------
# State Persistence
# ---------------------------------------------------------------------------

async def _persist_allocation(allocation: GPUAllocation, max_duration_hours: float):
    """Persist GPU allocation state to Redis."""
    redis = await get_redis()

    allocation_data = allocation.model_dump()
    allocation_data["max_duration_hours"] = max_duration_hours

    key = f"gpu_allocation:{allocation.allocation_id}"
    await redis.set(key, json.dumps(allocation_data))

    # Add to workspace's active allocations
    await redis.sadd(
        f"gpu_allocations:{allocation.workspace_id}",
        allocation.allocation_id
    )


async def get_allocation_state(allocation_id: str) -> Optional[Dict[str, Any]]:
    """Get GPU allocation state from Redis.

    Args:
        allocation_id: Allocation identifier

    Returns:
        Allocation state dictionary, or None if not found
    """
    redis = await get_redis()
    key = f"gpu_allocation:{allocation_id}"

    data = await redis.get(key)
    if data is None:
        return None

    return json.loads(data)


async def list_workspace_allocations(workspace_id: str) -> List[Dict[str, Any]]:
    """List all GPU allocations for a workspace.

    Args:
        workspace_id: Workspace identifier

    Returns:
        List of allocation state dictionaries
    """
    redis = await get_redis()
    key = f"gpu_allocations:{workspace_id}"

    allocation_ids = await redis.smembers(key)

    allocations = []
    for allocation_id in allocation_ids:
        state = await get_allocation_state(allocation_id)
        if state:
            allocations.append(state)

    return allocations


# ---------------------------------------------------------------------------
# Cost Guard Enforcement
# ---------------------------------------------------------------------------

async def allocate_gpu_with_cost_guard(
    request: GPUResourceRequest,
) -> Dict[str, Any]:
    """Allocate GPU with cost guard enforcement.

    Args:
        request: GPU resource request

    Returns:
        Allocation result or rejection
    """
    # Check cost guard limits
    allowed, reason = await check_cost_guard_limits(request)

    if not allowed:
        return {
            "status": "rejected",
            "reason": reason,
        }

    try:
        # Allocate GPU
        allocation = await allocate_gpu(request)

        return {
            "status": "allocated",
            "allocation": allocation.model_dump(),
        }
    except RuntimeError as e:
        return {
            "status": "rejected",
            "reason": str(e),
        }
