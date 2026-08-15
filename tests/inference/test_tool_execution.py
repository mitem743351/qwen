"""Phase 9.4 transactional tool-execution reliability tests."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from qwen_research.common.ids import TaskId
from qwen_research.domain.inference import InferencePolicy, InferenceRequest, ToolCall
from qwen_research.research.tool_execution import (
    ClaimOutcome,
    InMemoryToolExecutionStore,
    SqliteToolExecutionStore,
    ToolExecutionIdentity,
    ToolExecutionSemantics,
    ToolExecutionState,
    canonical_arguments_hash,
)
from qwen_research.research.tool_loop import (
    ANALYSIS,
    ToolExecutionResult,
    ToolExecutionStatus,
    run_tool_loop,
)
from qwen_research.tools.base import ToolPermission, ToolResult


class _CounterTool:
    name = "search_corpus"
    description = "counter tool"
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}
    permission = ToolPermission.READ
    model_callable = True
    execution_semantics = ToolExecutionSemantics.READ_ONLY

    def __init__(
        self, counter: dict[str, int], semantics: ToolExecutionSemantics | None = None
    ) -> None:
        self.counter = counter
        if semantics is not None:
            self.execution_semantics = semantics

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.counter["n"] += 1
        return ToolResult.success({"rows": 1})


def _request() -> InferenceRequest:
    return InferenceRequest(
        task_reference=TaskId("task_1"), inference_policy=InferencePolicy()
    )


def _tool_result(
    call_id: str, *, status: ToolExecutionStatus = ToolExecutionStatus.SUCCEEDED
) -> ToolExecutionResult:
    return ToolExecutionResult(call_id=call_id, tool_name="search_corpus", status=status)


def test_concurrent_duplicate_executes_once() -> None:
    store = InMemoryToolExecutionStore()
    counter: dict[str, int] = {"n": 0}
    barrier = threading.Barrier(2)
    identity = ToolExecutionIdentity("session-1", "call-1")

    def worker(owner: str) -> None:
        barrier.wait()
        claim = store.claim(
            identity,
            tool_name="search_corpus",
            arguments_hash=canonical_arguments_hash({"query": "q"}),
            project_id="default",
            session_id="",
            task_id=None,
            run_id=None,
            execution_semantics=ToolExecutionSemantics.READ_ONLY,
            permission="read",
            lease_id=f"lease-{owner}",
            lease_owner=owner,
            lease_duration_seconds=120.0,
        )
        if claim.outcome is ClaimOutcome.CLAIMED:
            counter["n"] += 1  # the actual side effect
            store.complete(identity, claim.lease_id or "", _tool_result("call-1"))

    threads = [threading.Thread(target=worker, args=(f"owner-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert counter["n"] == 1  # exactly one physical execution


def test_crash_after_execution_before_complete_is_unknown(tmp_path: Path) -> None:
    """A side-effecting call that crashes before completion is UNKNOWN, not retried."""
    path = tmp_path / "tool_exec.db"
    identity = ToolExecutionIdentity("session-1", "call-1")
    store_a = SqliteToolExecutionStore(path)
    store_a.initialize()
    store_a.claim(
        identity,
        tool_name="save_research_memory",
        arguments_hash=canonical_arguments_hash({"content": "x"}),
        project_id="default",
        session_id="",
        task_id=None,
        run_id=None,
        execution_semantics=ToolExecutionSemantics.SIDE_EFFECTING,
        permission="write",
        lease_id="lease-1",
        lease_owner="owner-a",
        lease_duration_seconds=0.01,
    )
    store_a.mark_running(identity, "lease-1")
    # Simulated crash: the external side effect happened, complete() never ran.
    store_a.close()

    # Restart with the same store; the lease has since expired (stale).
    time.sleep(0.05)
    store_b = SqliteToolExecutionStore(path)
    store_b.initialize()
    record = store_b.inspect(identity)
    assert record is not None
    assert record.state is ToolExecutionState.RUNNING
    assert store_b.is_stale(identity) is True
    # A new claim on a side-effecting tool must NOT silently re-execute.
    claim = store_b.claim(
        identity,
        tool_name="save_research_memory",
        arguments_hash=canonical_arguments_hash({"content": "x"}),
        project_id="default",
        session_id="",
        task_id=None,
        run_id=None,
        execution_semantics=ToolExecutionSemantics.SIDE_EFFECTING,
        permission="write",
        lease_id="lease-2",
        lease_owner="owner-b",
        lease_duration_seconds=120.0,
    )
    assert claim.outcome is ClaimOutcome.STALE  # stale, not auto-reclaimed
    # Recovery authority records UNKNOWN rather than re-executing.
    store_b.recover_unknown(identity, "crash before completion")
    record = store_b.inspect(identity)
    assert record is not None
    assert record.state is ToolExecutionState.UNKNOWN


def test_stale_read_only_reclaims_safely(tmp_path: Path) -> None:
    path = tmp_path / "tool_exec.db"
    identity = ToolExecutionIdentity("session-1", "call-1")
    store = SqliteToolExecutionStore(path)
    store.initialize()
    store.claim(
        identity,
        tool_name="search_corpus",
        arguments_hash=canonical_arguments_hash({"query": "q"}),
        project_id="default",
        session_id="",
        task_id=None,
        run_id=None,
        execution_semantics=ToolExecutionSemantics.READ_ONLY,
        permission="read",
        lease_id="lease-1",
        lease_owner="owner-a",
        lease_duration_seconds=-1.0,  # immediately stale
    )
    assert store.is_stale(identity) is True
    reclaim = store.reclaim(
        identity, lease_id="lease-2", lease_owner="owner-b", lease_duration_seconds=120.0
    )
    assert reclaim.outcome is ClaimOutcome.CLAIMED
    store.complete(identity, "lease-2", _tool_result("call-1"))


def test_old_owner_cannot_complete_after_reclaim(tmp_path: Path) -> None:
    import pytest

    from qwen_research.research.tool_execution import LeaseOwnershipError

    path = tmp_path / "tool_exec.db"
    identity = ToolExecutionIdentity("session-1", "call-1")
    store = SqliteToolExecutionStore(path)
    store.initialize()
    store.claim(
        identity,
        tool_name="search_corpus",
        arguments_hash=canonical_arguments_hash({"query": "q"}),
        project_id="default",
        session_id="",
        task_id=None,
        run_id=None,
        execution_semantics=ToolExecutionSemantics.READ_ONLY,
        permission="read",
        lease_id="lease-a",
        lease_owner="owner-a",
        lease_duration_seconds=-1.0,
    )
    store.reclaim(identity, lease_id="lease-b", lease_owner="owner-b", lease_duration_seconds=120.0)
    with pytest.raises(LeaseOwnershipError):
        store.complete(identity, "lease-a", _tool_result("call-1"))


def test_workflow_restart_replays_no_duplicate(tmp_path: Path) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool_exec.db")
    store.initialize()
    counter: dict[str, int] = {"n": 0}
    call = ToolCall(call_id="call-1", tool_name="search_corpus", arguments={"query": "q"})
    # First "workflow run" executes the tool.
    run_tool_loop(
        _request(),
        invoke=lambda req: _result_with_calls((call,)) if _first(req) else _final(req),
        tools=_registry(_CounterTool(counter)),
        profile=ANALYSIS,
        store=store,
        inference_session_id="session-1",
    )
    assert counter["n"] == 1

    # "Restart" — same session id and call id, fresh tool instance.
    counter2: dict[str, int] = {"n": 0}
    run_tool_loop(
        _request(),
        invoke=lambda req: _result_with_calls((call,)) if _first(req) else _final(req),
        tools=_registry(_CounterTool(counter2)),
        profile=ANALYSIS,
        store=store,
        inference_session_id="session-1",
    )
    assert counter2["n"] == 0  # replayed, never re-executed


def _first(req: InferenceRequest) -> bool:
    return not any(m.role.value == "tool" for m in req.messages)


def _final(req: InferenceRequest) -> Any:
    from qwen_research.domain.inference import InferenceResult

    return InferenceResult(status="ok", model="qwen3.7-max", content="final", finish_reason="stop")


def _result_with_calls(calls: tuple[ToolCall, ...]) -> Any:
    from qwen_research.domain.inference import InferenceResult

    return InferenceResult(
        status="ok",
        model="qwen3.7-max",
        content="",
        tool_calls_structured=calls,
        finish_reason="tool_calls",
    )


def _registry(tool: Any) -> Any:
    from qwen_research.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(tool)
    return registry
