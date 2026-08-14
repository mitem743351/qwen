"""Research Runtime contract: task lifecycle and unsupported operations."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import ClaimId
from qwen_research.domain.errors import UnsupportedOperationError
from qwen_research.domain.task import TaskStatus
from qwen_research.research.interfaces import MCPRequest, MCPResult
from qwen_research.research.runtime import InMemoryResearchRuntime


def test_execute_task_creates_classified_planned(runtime: InMemoryResearchRuntime) -> None:
    task = runtime.execute_task("Research the market for X")
    assert task.status is TaskStatus.PLANNED
    assert runtime.inspect_task(task.task_id) == task
    state = runtime.get_state(task.task_id)
    assert state.plan is not None
    assert state.current_stage is TaskStatus.PLANNED


def test_continue_task_advances_state(runtime: InMemoryResearchRuntime) -> None:
    task = runtime.execute_task("t")
    task = runtime.continue_task(task.task_id)
    assert task.status is TaskStatus.RETRIEVING
    assert runtime.get_state(task.task_id).current_stage is TaskStatus.RETRIEVING


def test_continue_to_completion(runtime: InMemoryResearchRuntime) -> None:
    task = runtime.execute_task("t")
    while not task.is_terminal:
        task = runtime.continue_task(task.task_id)
    assert task.status is TaskStatus.COMPLETED


def test_retrieve_context_is_unsupported(runtime: InMemoryResearchRuntime) -> None:
    task = runtime.execute_task("t")
    with pytest.raises(UnsupportedOperationError):
        runtime.retrieve_context(task.task_id)


def test_verify_claim_is_unsupported(runtime: InMemoryResearchRuntime) -> None:
    with pytest.raises(UnsupportedOperationError):
        runtime.verify_claim(ClaimId("claim_1"))


def test_mcp_contracts_are_domain_objects() -> None:
    request = MCPRequest(tool="get_research_state", arguments={"task_id": "task_1"})
    result = MCPResult(status="ok", result={"status": "planned"})
    assert request.tool == "get_research_state"
    assert result.status == "ok"


def test_runtime_is_transport_independent(runtime: InMemoryResearchRuntime) -> None:
    # The same API is callable without any MCP/Qwen/network involvement.
    task = runtime.execute_task("transport-independent check")
    assert runtime.inspect_task(task.task_id).status is TaskStatus.PLANNED
