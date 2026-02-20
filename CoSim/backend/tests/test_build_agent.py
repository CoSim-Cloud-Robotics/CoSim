"""Tests for the C++ Build Agent service layer and API.

TDD: These tests define the expected behaviour of the build agent
before the implementation exists.
"""
from __future__ import annotations

import asyncio
import os
import textwrap

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
# Service-layer tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_request_schema():
    """BuildRequest validates required fields."""
    from co_sim.services.build_agent import BuildRequest

    req = BuildRequest(
        workspace_id="ws-1",
        source_files={"main.cpp": '#include <iostream>\nint main() { std::cout << "hi"; }'},
        compiler="g++",
        flags=["-std=c++17", "-Wall"],
        output_name="main",
    )
    assert req.compiler in ("g++", "clang++")
    assert req.output_name == "main"
    assert "-std=c++17" in req.flags


@pytest.mark.asyncio
async def test_build_result_schema():
    """BuildResult captures success, artifacts, and logs."""
    from co_sim.services.build_agent import BuildResult

    result = BuildResult(
        status="success",
        exit_code=0,
        stdout="",
        stderr="",
        artifact_path="/tmp/builds/ws-1/main",
        compile_commands=None,
    )
    assert result.status == "success"
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_build_success(tmp_path):
    """A valid C++ file compiles to an executable."""
    from co_sim.services.build_agent import BuildRequest, compile_cpp

    source = textwrap.dedent("""\
        #include <iostream>
        int main() {
            std::cout << "hello build" << std::endl;
            return 0;
        }
    """)

    req = BuildRequest(
        workspace_id="ws-test",
        source_files={"main.cpp": source},
        compiler="g++",
        flags=["-std=c++17"],
        output_name="test_binary",
    )

    result = await compile_cpp(req, build_root=str(tmp_path))
    assert result.status == "success"
    assert result.exit_code == 0
    assert result.artifact_path is not None
    assert os.path.isfile(result.artifact_path)


@pytest.mark.asyncio
async def test_build_failure(tmp_path):
    """Invalid C++ triggers a compilation error."""
    from co_sim.services.build_agent import BuildRequest, compile_cpp

    bad_source = "int main() { this_is_not_valid; }"

    req = BuildRequest(
        workspace_id="ws-bad",
        source_files={"bad.cpp": bad_source},
        compiler="g++",
        flags=["-std=c++17"],
        output_name="bad_binary",
    )

    result = await compile_cpp(req, build_root=str(tmp_path))
    assert result.status == "error"
    assert result.exit_code != 0
    assert result.stderr  # should contain compiler error message


@pytest.mark.asyncio
async def test_compile_commands_json(tmp_path):
    """When requested, a compile_commands.json is generated."""
    from co_sim.services.build_agent import BuildRequest, compile_cpp

    source = '#include <cstdio>\nint main() { printf("ok"); }'

    req = BuildRequest(
        workspace_id="ws-cc",
        source_files={"main.cpp": source},
        compiler="g++",
        flags=["-std=c++17"],
        output_name="cc_test",
        generate_compile_commands=True,
    )

    result = await compile_cpp(req, build_root=str(tmp_path))
    assert result.status == "success"
    assert result.compile_commands is not None
    assert len(result.compile_commands) > 0
    assert result.compile_commands[0]["file"].endswith("main.cpp")


@pytest.mark.asyncio
async def test_execute_binary(tmp_path):
    """Compiled binary can be executed and stdout captured."""
    from co_sim.services.build_agent import BuildRequest, compile_cpp, execute_binary

    source = textwrap.dedent("""\
        #include <iostream>
        int main() {
            std::cout << "exec_output" << std::endl;
            return 0;
        }
    """)

    req = BuildRequest(
        workspace_id="ws-exec",
        source_files={"main.cpp": source},
        compiler="g++",
        flags=["-std=c++17"],
        output_name="run_me",
    )

    build_result = await compile_cpp(req, build_root=str(tmp_path))
    assert build_result.status == "success"

    exec_result = await execute_binary(build_result.artifact_path, timeout=10)
    assert exec_result["exit_code"] == 0
    assert "exec_output" in exec_result["stdout"]


@pytest.mark.asyncio
async def test_build_state_persisted_in_redis():
    """Build status is persisted to Redis for cross-service visibility."""
    from co_sim.services.build_agent import persist_build_status, get_build_status

    await persist_build_status("ws-1", "build-abc", status="running")
    state = await get_build_status("ws-1", "build-abc")
    assert state is not None
    assert state["status"] == "running"

    await persist_build_status("ws-1", "build-abc", status="success", artifact="/tmp/out")
    state = await get_build_status("ws-1", "build-abc")
    assert state["status"] == "success"
    assert state["artifact"] == "/tmp/out"


@pytest.mark.asyncio
async def test_multi_file_build(tmp_path):
    """Multiple source files compile and link together."""
    from co_sim.services.build_agent import BuildRequest, compile_cpp

    header = 'int add(int a, int b);'
    impl = '#include "math_utils.h"\nint add(int a, int b) { return a + b; }'
    main = textwrap.dedent("""\
        #include <iostream>
        #include "math_utils.h"
        int main() {
            std::cout << add(2, 3) << std::endl;
            return 0;
        }
    """)

    req = BuildRequest(
        workspace_id="ws-multi",
        source_files={
            "math_utils.h": header,
            "math_utils.cpp": impl,
            "main.cpp": main,
        },
        compiler="g++",
        flags=["-std=c++17"],
        output_name="multi_test",
    )

    result = await compile_cpp(req, build_root=str(tmp_path))
    assert result.status == "success"
    assert result.exit_code == 0
