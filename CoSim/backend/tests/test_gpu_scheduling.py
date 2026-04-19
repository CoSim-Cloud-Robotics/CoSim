"""Tests for GPU Scheduling Agent service layer and API.

TDD: These tests define the expected behaviour of GPU scheduling
before the implementation exists.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from co_sim.core import redis as redis_helpers


@pytest_asyncio.fixture(autouse=True)
async def _redis_state():
    await redis_helpers.reset_redis_state()
    redis_helpers.set_redis_factory(lambda _: FakeRedis(decode_responses=True))
    await redis_helpers.init_redis(force=True)
    yield
    await redis_helpers.reset_redis_state()


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gpu_resource_request_schema():
    """GPUResourceRequest validates required fields."""
    from co_sim.services.gpu_scheduling import GPUResourceRequest

    req = GPUResourceRequest(
        workspace_id="ws-1",
        task_id="train-ppo-1",
        gpu_count=1,
        gpu_memory_gb=8,
        max_duration_hours=24,
    )
    assert req.gpu_count > 0
    assert req.gpu_memory_gb > 0
    assert req.max_duration_hours > 0


@pytest.mark.asyncio
async def test_gpu_allocation_schema():
    """GPUAllocation captures allocated GPU resources."""
    from co_sim.services.gpu_scheduling import GPUAllocation

    alloc = GPUAllocation(
        allocation_id="alloc-abc",
        workspace_id="ws-1",
        task_id="train-ppo-1",
        gpu_ids=["gpu-0"],
        gpu_memory_allocated_gb=8,
        status="running",
    )
    assert alloc.status in ("pending", "running", "completed", "failed", "terminated")
    assert len(alloc.gpu_ids) > 0


@pytest.mark.asyncio
async def test_cost_guard_policy_schema():
    """CostGuardPolicy validates spending limits."""
    from co_sim.services.gpu_scheduling import CostGuardPolicy

    policy = CostGuardPolicy(
        workspace_id="ws-1",
        max_concurrent_gpus=4,
        max_spend_per_day_usd=100.0,
        max_spend_per_task_usd=50.0,
        alert_threshold_usd=80.0,
    )
    assert policy.max_concurrent_gpus > 0
    assert policy.max_spend_per_day_usd > 0


# ---------------------------------------------------------------------------
# GPU availability and allocation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_gpu_availability():
    """Check if GPU resources are available."""
    from co_sim.services.gpu_scheduling import check_gpu_availability

    available = await check_gpu_availability(gpu_count=1, gpu_memory_gb=8)
    assert isinstance(available, bool)


@pytest.mark.asyncio
async def test_list_available_gpus():
    """List all available GPUs in the cluster."""
    from co_sim.services.gpu_scheduling import list_available_gpus

    gpus = await list_available_gpus()
    assert isinstance(gpus, list)
    # Each GPU should have id, memory, status
    for gpu in gpus:
        assert "gpu_id" in gpu
        assert "memory_gb" in gpu
        assert "status" in gpu


@pytest.mark.asyncio
async def test_allocate_gpu():
    """Allocate GPU resources for a task."""
    from co_sim.services.gpu_scheduling import (
        GPUResourceRequest,
        allocate_gpu,
    )

    req = GPUResourceRequest(
        workspace_id="ws-alloc",
        task_id="task-1",
        gpu_count=1,
        gpu_memory_gb=8,
        max_duration_hours=2,
    )

    allocation = await allocate_gpu(req)
    assert allocation.allocation_id is not None
    assert allocation.workspace_id == "ws-alloc"
    assert allocation.task_id == "task-1"
    assert len(allocation.gpu_ids) == 1
    assert allocation.status == "running"


@pytest.mark.asyncio
async def test_release_gpu():
    """Release GPU resources after task completion."""
    from co_sim.services.gpu_scheduling import (
        GPUResourceRequest,
        allocate_gpu,
        release_gpu,
    )

    req = GPUResourceRequest(
        workspace_id="ws-release",
        task_id="task-2",
        gpu_count=1,
        gpu_memory_gb=4,
    )

    allocation = await allocate_gpu(req)
    allocation_id = allocation.allocation_id

    result = await release_gpu(allocation_id)
    assert result["status"] == "released"
    assert result["allocation_id"] == allocation_id


# ---------------------------------------------------------------------------
# Cost guard policy tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_cost_guard_policy():
    """Set cost guard policy for a workspace."""
    from co_sim.services.gpu_scheduling import (
        CostGuardPolicy,
        set_cost_guard_policy,
    )

    policy = CostGuardPolicy(
        workspace_id="ws-cost",
        max_concurrent_gpus=2,
        max_spend_per_day_usd=50.0,
        max_spend_per_task_usd=25.0,
        alert_threshold_usd=40.0,
    )

    await set_cost_guard_policy(policy)

    # Verify policy was set (will be checked by get_cost_guard_policy)
    assert True  # Policy setting succeeded without error


@pytest.mark.asyncio
async def test_get_cost_guard_policy():
    """Get cost guard policy for a workspace."""
    from co_sim.services.gpu_scheduling import (
        CostGuardPolicy,
        set_cost_guard_policy,
        get_cost_guard_policy,
    )

    policy = CostGuardPolicy(
        workspace_id="ws-get-cost",
        max_concurrent_gpus=3,
        max_spend_per_day_usd=75.0,
    )

    await set_cost_guard_policy(policy)
    retrieved = await get_cost_guard_policy("ws-get-cost")

    assert retrieved is not None
    assert retrieved["max_concurrent_gpus"] == 3
    assert retrieved["max_spend_per_day_usd"] == 75.0


@pytest.mark.asyncio
async def test_check_cost_guard_limits():
    """Verify cost guard prevents exceeding limits."""
    from co_sim.services.gpu_scheduling import (
        CostGuardPolicy,
        GPUResourceRequest,
        set_cost_guard_policy,
        check_cost_guard_limits,
    )

    # Set strict policy
    policy = CostGuardPolicy(
        workspace_id="ws-strict",
        max_concurrent_gpus=1,
        max_spend_per_day_usd=10.0,
    )
    await set_cost_guard_policy(policy)

    # Request that should pass
    req1 = GPUResourceRequest(
        workspace_id="ws-strict",
        task_id="task-ok",
        gpu_count=1,
        gpu_memory_gb=4,
    )
    allowed, reason = await check_cost_guard_limits(req1)
    assert allowed is True

    # Request that exceeds GPU limit
    req2 = GPUResourceRequest(
        workspace_id="ws-strict",
        task_id="task-exceed",
        gpu_count=2,  # Exceeds max_concurrent_gpus
        gpu_memory_gb=4,
    )
    allowed, reason = await check_cost_guard_limits(req2)
    assert allowed is False
    assert "concurrent gpu" in reason.lower()


# ---------------------------------------------------------------------------
# Cost tracking tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_track_gpu_cost():
    """Track GPU usage cost for billing."""
    from co_sim.services.gpu_scheduling import track_gpu_cost

    await track_gpu_cost(
        workspace_id="ws-billing",
        allocation_id="alloc-123",
        gpu_hours=2.5,
        cost_usd=5.0,
    )

    # Cost tracked successfully
    assert True


@pytest.mark.asyncio
async def test_get_workspace_gpu_spend():
    """Get total GPU spend for a workspace."""
    from co_sim.services.gpu_scheduling import (
        track_gpu_cost,
        get_workspace_gpu_spend,
    )

    # Track some costs
    await track_gpu_cost("ws-spend", "alloc-1", gpu_hours=1.0, cost_usd=2.0)
    await track_gpu_cost("ws-spend", "alloc-2", gpu_hours=2.0, cost_usd=4.0)

    spend = await get_workspace_gpu_spend("ws-spend")
    assert spend["total_cost_usd"] == 6.0
    assert spend["total_gpu_hours"] == 3.0


# ---------------------------------------------------------------------------
# Resource limits and monitoring tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_monitor_gpu_allocation():
    """Monitor GPU allocation status."""
    from co_sim.services.gpu_scheduling import (
        GPUResourceRequest,
        allocate_gpu,
        monitor_gpu_allocation,
    )

    req = GPUResourceRequest(
        workspace_id="ws-monitor",
        task_id="task-monitor",
        gpu_count=1,
        gpu_memory_gb=4,
    )

    allocation = await allocate_gpu(req)
    status = await monitor_gpu_allocation(allocation.allocation_id)

    assert status is not None
    assert status["allocation_id"] == allocation.allocation_id
    assert status["status"] == "running"
    assert "gpu_utilization" in status


@pytest.mark.asyncio
async def test_terminate_allocation_on_timeout():
    """Terminate GPU allocation when max duration is exceeded."""
    from co_sim.services.gpu_scheduling import (
        GPUResourceRequest,
        allocate_gpu,
        check_allocation_timeout,
    )

    req = GPUResourceRequest(
        workspace_id="ws-timeout",
        task_id="task-timeout",
        gpu_count=1,
        gpu_memory_gb=4,
        max_duration_hours=0.001,  # Very short timeout for testing
    )

    allocation = await allocate_gpu(req)

    # Check timeout (in real system, this would be called periodically)
    import asyncio
    await asyncio.sleep(0.1)  # Wait slightly

    timed_out = await check_allocation_timeout(allocation.allocation_id)
    assert isinstance(timed_out, bool)


# ---------------------------------------------------------------------------
# State persistence in Redis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_allocation_state():
    """GPU allocation state is persisted to Redis."""
    from co_sim.services.gpu_scheduling import (
        GPUResourceRequest,
        allocate_gpu,
        get_allocation_state,
    )

    req = GPUResourceRequest(
        workspace_id="ws-persist",
        task_id="task-persist",
        gpu_count=1,
        gpu_memory_gb=8,
    )

    allocation = await allocate_gpu(req)
    state = await get_allocation_state(allocation.allocation_id)

    assert state is not None
    assert state["allocation_id"] == allocation.allocation_id
    assert state["workspace_id"] == "ws-persist"
    assert state["status"] == "running"


@pytest.mark.asyncio
async def test_list_workspace_allocations():
    """List all GPU allocations for a workspace."""
    from co_sim.services.gpu_scheduling import (
        GPUResourceRequest,
        allocate_gpu,
        list_workspace_allocations,
    )

    # Create multiple allocations
    for i in range(3):
        req = GPUResourceRequest(
            workspace_id="ws-list",
            task_id=f"task-{i}",
            gpu_count=1,
            gpu_memory_gb=4,
        )
        await allocate_gpu(req)

    allocations = await list_workspace_allocations("ws-list")
    assert len(allocations) == 3
    assert all(a["workspace_id"] == "ws-list" for a in allocations)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gpu_scheduling_workflow():
    """Complete workflow: check availability, allocate, monitor, release."""
    from co_sim.services.gpu_scheduling import (
        GPUResourceRequest,
        check_gpu_availability,
        allocate_gpu,
        monitor_gpu_allocation,
        release_gpu,
    )

    # 1. Check availability
    available = await check_gpu_availability(gpu_count=1, gpu_memory_gb=4)
    assert available is True

    # 2. Allocate GPU
    req = GPUResourceRequest(
        workspace_id="ws-workflow",
        task_id="workflow-task",
        gpu_count=1,
        gpu_memory_gb=4,
        max_duration_hours=1,
    )
    allocation = await allocate_gpu(req)
    assert allocation.status == "running"

    # 3. Monitor
    status = await monitor_gpu_allocation(allocation.allocation_id)
    assert status["status"] == "running"

    # 4. Release
    result = await release_gpu(allocation.allocation_id)
    assert result["status"] == "released"


@pytest.mark.asyncio
async def test_cost_guard_enforcement():
    """Cost guard prevents allocation when limits are exceeded."""
    from co_sim.services.gpu_scheduling import (
        CostGuardPolicy,
        GPUResourceRequest,
        set_cost_guard_policy,
        check_cost_guard_limits,
        allocate_gpu_with_cost_guard,
    )

    # Set policy
    policy = CostGuardPolicy(
        workspace_id="ws-guard",
        max_concurrent_gpus=1,
        max_spend_per_day_usd=20.0,
    )
    await set_cost_guard_policy(policy)

    # First allocation should succeed
    req1 = GPUResourceRequest(
        workspace_id="ws-guard",
        task_id="task-1",
        gpu_count=1,
        gpu_memory_gb=4,
    )
    result1 = await allocate_gpu_with_cost_guard(req1)
    assert result1["status"] == "allocated"

    # Second allocation should fail (exceeds concurrent GPU limit)
    req2 = GPUResourceRequest(
        workspace_id="ws-guard",
        task_id="task-2",
        gpu_count=1,
        gpu_memory_gb=4,
    )
    result2 = await allocate_gpu_with_cost_guard(req2)
    assert result2["status"] == "rejected"
    assert "limit" in result2["reason"].lower()
