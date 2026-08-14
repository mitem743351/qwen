"""Research Runtime contract: protocol/implementation agreement, task lifecycle,
session handling, and unsupported operations."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import ClaimId
from qwen_research.domain.errors import UnsupportedOperationError
from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import DEEP
from qwen_research.domain.task import TaskStatus
from qwen_research.research.interfaces import MCPRequest, MCPResult, ResearchRuntime
from qwen_research.research.runtime import InMemoryResearchRuntime


def test_runtime_satisfies_research_runtime_protocol() -> None:
    # The concrete implementation must satisfy the public protocol (and its
    # signatures must agree — verified by static typing and these calls).
    runtime = InMemoryResearchRuntime()
    assert isinstance(runtime, ResearchRuntime)


def _conforms_to_protocol(runtime: ResearchRuntime) -> None:
    # Static conformance assertion: mypy rejects this call if the concrete
    # implementation's signatures diverge from the ResearchRuntime protocol.
    _ = runtime


def test_protocol_conformance_is_statically_checked() -> None:
    _conforms_to_protocol(InMemoryResearchRuntime())


def test_create_session_defaults() -> None:
    runtime = InMemoryResearchRuntime()
    session = runtime.create_session()
    assert session.project_id == "default"
    assert session.mode is OperatingMode.STUDIO_NATIVE


def test_create_session_with_mode() -> None:
    runtime = InMemoryResearchRuntime()
    session = runtime.create_session(mode=OperatingMode.GATEWAY_INFERENCE)
    assert session.mode is OperatingMode.GATEWAY_INFERENCE


def test_create_session_with_project() -> None:
    runtime = InMemoryResearchRuntime()
    session = runtime.create_session(project_id="papers-2026")
    assert session.project_id == "papers-2026"


def test_execute_task_with_session_id() -> None:
    runtime = InMemoryResearchRuntime()
    session = runtime.create_session(project_id="p1")
    task = runtime.execute_task("research q", session_id=session.session_id)
    assert task.session_id == session.session_id


def test_execute_task_defaults_and_profile() -> None:
    runtime = InMemoryResearchRuntime()
    task = runtime.execute_task("research q")
    assert task.reasoning_profile == "DEEP"
    assert task.status is TaskStatus.PLANNED

    task2 = runtime.execute_task("research q2", profile=DEEP)
    assert task2.reasoning_profile == "DEEP"
    # A distinct session was auto-created for the un-scoped task.
    assert task.session_id != task2.session_id


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
        runtime.verify_claim("default", ClaimId("claim_1"))


@pytest.mark.parametrize(
    "method",
    [
        "pause_task",
        "resume_task",
        "wait_for_input",
        "cancel_task",
    ],
)
def test_reserved_lifecycle_operations_are_unsupported(
    runtime: InMemoryResearchRuntime, method: str
) -> None:
    task = runtime.execute_task("t")
    with pytest.raises(UnsupportedOperationError):
        getattr(runtime, method)(task.task_id)


def test_provide_input_is_unsupported(runtime: InMemoryResearchRuntime) -> None:
    task = runtime.execute_task("t")
    with pytest.raises(UnsupportedOperationError):
        runtime.provide_input(task.task_id, {"answer": "x"})


def test_mcp_contracts_are_domain_objects() -> None:
    request = MCPRequest(tool="get_research_state", arguments={"task_id": "task_1"})
    result = MCPResult(status="ok", result={"status": "planned"})
    assert request.tool == "get_research_state"
    assert result.status == "ok"


def test_runtime_is_transport_independent(runtime: InMemoryResearchRuntime) -> None:
    # The same API is callable without any MCP/Qwen/network involvement.
    task = runtime.execute_task("transport-independent check")
    assert runtime.inspect_task(task.task_id).status is TaskStatus.PLANNED
