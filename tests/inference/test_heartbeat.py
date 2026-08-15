"""Phase 9.5 lease heartbeat / long-running execution tests."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from qwen_research.common.ids import TaskId
from qwen_research.domain.errors import ConfigurationError
from qwen_research.domain.inference import InferencePolicy, InferenceRequest, ToolCall
from qwen_research.research.tool_execution import (
    ClaimOutcome,
    InMemoryToolExecutionStore,
    LeaseHeartbeat,
    LeaseOwnershipError,
    SqliteToolExecutionStore,
    ToolExecutionIdentity,
    ToolExecutionSemantics,
    ToolExecutionState,
    canonical_arguments_hash,
)
from qwen_research.research.tool_loop import (
    ANALYSIS,
    LoopStatus,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolLoopConfig,
    run_tool_loop,
)
from qwen_research.tools.base import ToolPermission, ToolResult


class _SlowTool:
    name = "search_corpus"
    description = "slow tool"
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}
    permission = ToolPermission.READ
    model_callable = True
    execution_semantics = ToolExecutionSemantics.READ_ONLY

    def __init__(
        self,
        *,
        sleep: float,
        counter: dict[str, int] | None = None,
        semantics: ToolExecutionSemantics | None = None,
    ) -> None:
        self._sleep = sleep
        self.counter = counter if counter is not None else {"n": 0}
        if semantics is not None:
            self.execution_semantics = semantics

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.counter["n"] += 1
        time.sleep(self._sleep)
        return ToolResult.success({"ok": True})


def _identity(session: str = "session-1", call: str = "call_1") -> ToolExecutionIdentity:
    return ToolExecutionIdentity(inference_session_id=session, call_id=call)


def _claim_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "tool_name": "search_corpus",
        "arguments_hash": canonical_arguments_hash({"query": "q"}),
        "project_id": "default",
        "session_id": "",
        "task_id": None,
        "run_id": None,
        "execution_semantics": ToolExecutionSemantics.READ_ONLY,
        "permission": "read",
        "lease_id": "lease-1",
        "lease_owner": "owner-1",
        "lease_duration_seconds": 120.0,
    }
    fields.update(overrides)
    return fields


def test_long_running_tool_renews_lease_no_false_reclaim() -> None:
    """A tool running longer than the lease stays owned via heartbeat."""
    store = InMemoryToolExecutionStore()
    counter: dict[str, int] = {"n": 0}
    identity = _identity()

    def worker() -> None:
        claim = store.claim(identity, **_claim_fields())
        assert claim.outcome is ClaimOutcome.CLAIMED
        store.mark_running(identity, "lease-1")
        hb = LeaseHeartbeat(
            store,
            identity,
            "lease-1",
            lease_duration_seconds=0.15,
            heartbeat_interval_seconds=0.03,
        )
        hb.start()
        time.sleep(0.4)  # > 2× lease duration
        assert hb.heartbeat_count >= 2
        assert hb.lost is False
        assert store.is_stale(identity) is False  # still owned (live heartbeat)
        hb.stop()
        store.complete(identity, "lease-1", ToolExecutionResult(
            call_id="call_1", tool_name="search_corpus", status=ToolExecutionStatus.SUCCEEDED
        ))
        counter["n"] += 1

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert counter["n"] == 1
    record = store.inspect(identity)
    assert record is not None
    assert record.state is ToolExecutionState.SUCCEEDED
    assert record.heartbeat_count >= 2


def test_competing_reclaim_denied_while_heartbeating() -> None:
    store = InMemoryToolExecutionStore()
    identity = _identity()
    claim = store.claim(identity, **_claim_fields(lease_id="lease-a", lease_owner="A"))
    assert claim.outcome is ClaimOutcome.CLAIMED
    store.mark_running(identity, "lease-a")
    hb = LeaseHeartbeat(
        store, identity, "lease-a", lease_duration_seconds=0.15, heartbeat_interval_seconds=0.03
    )
    hb.start()
    try:
        time.sleep(0.05)
        # B attempts to claim while A is actively heartbeating.
        b = store.claim(
            identity,
            **_claim_fields(lease_id="lease-b", lease_owner="B"),
        )
        assert b.outcome is ClaimOutcome.ALREADY_CLAIMED
    finally:
        hb.stop()


def test_genuine_stale_read_only_reclaims(tmp_path: Any) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(
        identity,
        **_claim_fields(
            lease_id="lease-a", lease_owner="A", lease_duration_seconds=-1.0  # already stale
        ),
    )
    assert store.is_stale(identity) is True
    reclaim = store.reclaim(
        identity, lease_id="lease-b", lease_owner="B", lease_duration_seconds=120.0
    )
    assert reclaim.outcome is ClaimOutcome.CLAIMED


def test_genuine_stale_side_effecting_marks_unknown(tmp_path: Any) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(
        identity,
        **_claim_fields(
            lease_id="lease-a",
            lease_owner="A",
            lease_duration_seconds=-1.0,
            execution_semantics=ToolExecutionSemantics.SIDE_EFFECTING,
            permission="write",
        ),
    )
    # Side-effecting stale claim must not be auto-reclaimed; mark UNKNOWN.
    store.recover_unknown(identity, "stale side-effecting execution")
    record = store.inspect(identity)
    assert record is not None
    assert record.state is ToolExecutionState.UNKNOWN


def test_old_owner_cannot_heartbeat_after_reclaim(tmp_path: Any) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(
        identity, **_claim_fields(lease_id="lease-a", lease_owner="A", lease_duration_seconds=-1.0)
    )
    store.reclaim(
        identity, lease_id="lease-b", lease_owner="B", lease_duration_seconds=120.0
    )
    with pytest.raises(LeaseOwnershipError):
        store.heartbeat(identity, "lease-a", 120.0)
    with pytest.raises(LeaseOwnershipError):
        store.complete(identity, "lease-a", ToolExecutionResult(
            call_id="call_1", tool_name="search_corpus", status=ToolExecutionStatus.SUCCEEDED
        ))


def test_heartbeat_after_terminal_is_noop() -> None:
    store = InMemoryToolExecutionStore()
    identity = _identity()
    store.claim(identity, **_claim_fields())
    store.mark_running(identity, "lease-1")
    store.complete(identity, "lease-1", ToolExecutionResult(
        call_id="call_1", tool_name="search_corpus", status=ToolExecutionStatus.SUCCEEDED
    ))
    # Heartbeat on a terminal record is rejected (no resurrection).
    with pytest.raises(LeaseOwnershipError):
        store.heartbeat(identity, "lease-1", 120.0)


def test_heartbeat_lost_on_store_failure() -> None:
    class _BrokenStore:
        def heartbeat(self, identity: Any, lease_id: str, lease_duration_seconds: float) -> None:
            raise RuntimeError("db unavailable")

    hb = LeaseHeartbeat(
        _BrokenStore(),  # type: ignore[arg-type]
        _identity(),
        "lease-1",
        lease_duration_seconds=10.0,
        heartbeat_interval_seconds=0.01,
        retries=2,
        retry_backoff_seconds=0.0,
    )
    hb.start()
    time.sleep(0.1)
    hb.stop()
    assert hb.lost is True
    assert hb.heartbeat_failures >= 2


def test_config_validation() -> None:
    with pytest.raises(ConfigurationError):
        ToolLoopConfig(lease_duration_seconds=0.0)
    with pytest.raises(ConfigurationError):
        ToolLoopConfig(heartbeat_interval_seconds=0.0)
    with pytest.raises(ConfigurationError):
        ToolLoopConfig(lease_duration_seconds=1.0, heartbeat_interval_seconds=2.0)


def test_tool_loop_long_running_no_duplicate() -> None:
    """End-to-end: a long tool stays leased and completes exactly once."""
    store = InMemoryToolExecutionStore()
    counter: dict[str, int] = {"n": 0}
    tool = _SlowTool(sleep=0.15, counter=counter)
    call = ToolCall(call_id="call-1", tool_name="search_corpus", arguments={"query": "q"})

    from qwen_research.tools.registry import ToolRegistry

    def invoke(req: InferenceRequest) -> Any:
        from qwen_research.domain.inference import InferenceResult
        if not any(m.role.value == "tool" for m in req.messages):
            return InferenceResult(
                status="ok", model="qwen3.7-max", content="",
                tool_calls_structured=(call,), finish_reason="tool_calls",
            )
        return InferenceResult(
            status="ok", model="qwen3.7-max", content="final", finish_reason="stop"
        )

    registry = ToolRegistry()
    registry.register(tool)
    request = InferenceRequest(task_reference=TaskId("task_1"), inference_policy=InferencePolicy())
    outcome = run_tool_loop(
        request,
        invoke=invoke,
        tools=registry,
        profile=ANALYSIS,
        store=store,
        inference_session_id="session-1",
        config=ToolLoopConfig(lease_duration_seconds=0.05, heartbeat_interval_seconds=0.015),
    )
    assert outcome.status is LoopStatus.FINAL
    assert counter["n"] == 1
    assert outcome.tool_results[0].status is ToolExecutionStatus.SUCCEEDED


def test_heartbeat_thread_clean_shutdown() -> None:
    store = InMemoryToolExecutionStore()
    identity = _identity()
    store.claim(identity, **_claim_fields())
    hb = LeaseHeartbeat(
        store, identity, "lease-1", lease_duration_seconds=10.0, heartbeat_interval_seconds=0.01
    )
    hb.start()
    hb.stop(timeout=5.0)
    assert hb._thread is not None
    assert not hb._thread.is_alive()
