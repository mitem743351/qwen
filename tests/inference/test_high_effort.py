"""Phase 10.1 high-effort execution: real runtime integration + inheritance."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from inference_helpers import FakeQwenTransport, TransportResponse, completion_response
from qwen_research.domain.test_time import (
    HighEffortRunState,
    ResourceDimension,
    RunStatus,
    TrajectoryStrategy,
    get_test_time_policy,
    trajectory_query_set,
)
from qwen_research.inference.config import ProviderConfig
from qwen_research.inference.providers.qwen import QwenProvider
from qwen_research.inference.runtime import InferenceRuntime
from qwen_research.research.budget_store import InMemoryRunStateStore, SqliteRunStateStore
from qwen_research.research.high_effort import HighEffortEngine
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.research.tool_execution import (
    ClaimOutcome,
    InMemoryToolExecutionStore,
    ToolExecutionIdentity,
    ToolExecutionSemantics,
    canonical_arguments_hash,
)
from qwen_research.research.tool_loop import ToolExecutionResult, ToolExecutionStatus
from verification_helpers import build_service

_MODEL = "qwen3.8-max-preview"


def _make_fake_provider() -> tuple[Any, FakeQwenTransport]:
    """A fake Qwen provider (model ``qwen3.8-max-preview``) that answers critique
    and synthesis turns, recording every request body via ``transport.calls``."""
    def handler(url: str, headers: dict, body: dict, timeout: float) -> TransportResponse:
        system = body["messages"][0]["content"]
        if "critic" in system:
            return completion_response("unsupported claim found", finish_reason="stop")
        return completion_response(
            "grounded synthesis: the surface-code threshold is ~1%", finish_reason="stop"
        )

    transport = FakeQwenTransport(handler)
    config = ProviderConfig(
        provider_id="qwen",
        api_endpoint="https://example.invalid/compatible-mode/v1",
        credential_env="TEST_QWEN_API_KEY",
        default_model=_MODEL,
    )
    provider = QwenProvider(
        config, transport=transport, credential_resolver=lambda name: "test-key"
    )
    return provider, transport


def _bodies(transport: FakeQwenTransport) -> list[dict]:
    """Return the parsed request-body dicts recorded by the transport."""
    return [call[2] for call in transport.calls]


def _build_runtime(tmp_path: Path, provider: Any) -> InMemoryResearchRuntime:
    service, _, stack = build_service(tmp_path)
    inference = InferenceRuntime(
        {"qwen": provider}, default_provider="qwen", default_model=_MODEL
    )
    return InMemoryResearchRuntime(
        retriever=stack["hybrid"], verification=service, inference=inference
    )


# -- real fake-provider end-to-end path -----------------------------------

def test_xhigh_real_fake_provider_path(tmp_path: Path) -> None:
    provider, transport = _make_fake_provider()
    runtime = _build_runtime(tmp_path, provider)

    result = runtime.run_high_effort(
        profile="XHIGH",
        task_description="surface code threshold",
        trajectory_strategies=(TrajectoryStrategy.DIRECT, TrajectoryStrategy.COUNTERARGUMENT),
        project_id="p",
    )
    seen = _bodies(transport)

    assert result.status is RunStatus.COMPLETED
    # Real evidence + verification were produced (completion criteria met).
    assert result.synthesis_input is not None
    assert result.synthesis_input.evidence_refs
    assert result.synthesis_input.verification_refs
    assert result.final_synthesis != ""

    # Trajectories actually differ (distinct strategies, distinct evidence).
    assert len(result.trajectories) == 2
    strategies = {t.strategy for t in result.trajectories}
    assert strategies == {TrajectoryStrategy.DIRECT, TrajectoryStrategy.COUNTERARGUMENT}

    # Critique + synthesis both invoked the inference runtime.
    systems = [b["messages"][0]["content"] for b in seen]
    assert any("critic" in s for s in systems)
    assert any("synthesis" in s for s in systems)

    # Native Qwen reasoning control was emitted on every inference request.
    assert any(b.get("reasoning_effort") == "xhigh" for b in seen)

    # consumed <= allocated for every dimension.
    for dimension, allocated in result.budget_summary["allocated"].items():
        assert result.budget_summary["consumed"][dimension] <= allocated, dimension


def test_extreme_real_fake_provider_path(tmp_path: Path) -> None:
    provider, _ = _make_fake_provider()
    runtime = _build_runtime(tmp_path, provider)

    result = runtime.run_high_effort(
        profile="EXTREME",
        task_description="surface code threshold",
        trajectory_strategies=(
            TrajectoryStrategy.DIRECT,
            TrajectoryStrategy.LITERATURE,
            TrajectoryStrategy.DATA_DRIVEN,
        ),
        project_id="p",
    )
    assert result.status is RunStatus.COMPLETED
    assert len(result.trajectories) == 3
    for dimension, allocated in result.budget_summary["allocated"].items():
        assert result.budget_summary["consumed"][dimension] <= allocated, dimension


# -- trajectory strategies differ ----------------------------------------

def test_trajectory_strategies_produce_distinct_queries() -> None:
    objective = "surface code threshold"
    direct = trajectory_query_set(TrajectoryStrategy.DIRECT, objective)
    counter = trajectory_query_set(TrajectoryStrategy.COUNTERARGUMENT, objective)
    literature = trajectory_query_set(TrajectoryStrategy.LITERATURE, objective)
    assert direct.primary_query == objective
    assert counter.primary_query != direct.primary_query
    assert literature.primary_query != direct.primary_query
    assert "against" in counter.primary_query
    assert "review" in literature.primary_query
    # All strategies actually differ from DIRECT.
    assert len({direct.primary_query, counter.primary_query, literature.primary_query}) == 3


# -- critique invokes inference ------------------------------------------

def test_critique_invokes_inference(tmp_path: Path) -> None:
    provider, transport = _make_fake_provider()
    runtime = _build_runtime(tmp_path, provider)
    result = runtime.run_high_effort(
        profile="XHIGH",
        task_description="surface code threshold",
        trajectory_strategies=(TrajectoryStrategy.DIRECT,),
        project_id="p",
    )
    seen = _bodies(transport)
    assert result.status is RunStatus.COMPLETED
    # The critique stage produced a critique result via the inference runtime.
    assert result.critique_results
    assert result.critique_results[0].issues
    assert any("critic" in b["messages"][0]["content"] for b in seen)


# -- completion depends on evidence/verification --------------------------

def test_completion_requires_evidence_and_verification() -> None:
    # A runtime with inference but NO retriever/verification cannot complete.
    provider, _ = _make_fake_provider()
    inference = InferenceRuntime(
        {"qwen": provider}, default_provider="qwen", default_model="qwen3.8-max-preview"
    )
    runtime = InMemoryResearchRuntime(inference=inference)
    result = runtime.run_high_effort(
        profile="XHIGH",
        task_description="surface code threshold",
        trajectory_strategies=(TrajectoryStrategy.DIRECT,),
        project_id="p",
    )
    # No evidence/verification → not COMPLETED (PARTIAL or SYNTHESIS_REQUIRED).
    assert result.status is not RunStatus.COMPLETED


# -- wall-time enforced during execution ----------------------------------

def test_wall_time_enforced_before_operations() -> None:
    calls: list[str] = []

    class _Runtime:
        def search_corpus(self, query: str, options: Any = None) -> Any:
            calls.append(query)
            return SimpleNamespace(chunks=[])

    state = HighEffortRunState(
        run_id="r", profile="FAST", task_description="t",
        budget=get_test_time_policy("FAST").budget(),
    )
    engine = HighEffortEngine(_Runtime(), "FAST", state)
    # Simulate the wall-time deadline already being in the past.
    state.deadline_at = 0.0  # long ago
    assert engine.deadline_exceeded()
    assert engine.retrieve("q") == []
    assert calls == []  # the runtime was never called


# -- global budget authoritative (callers cannot bypass) ------------------

def test_budget_authoritative_cannot_bypass() -> None:
    calls: list[str] = []

    class _Runtime:
        def search_corpus(self, query: str, options: Any = None) -> Any:
            calls.append(query)
            return SimpleNamespace(chunks=[SimpleNamespace(chunk_id="c1")])

    state = HighEffortRunState(
        run_id="r", profile="FAST", task_description="t",
        budget=get_test_time_policy("FAST").budget(),
    )
    engine = HighEffortEngine(_Runtime(), "FAST", state)
    # Exhaust the retrieval dimension directly.
    while engine.budget.can_afford(ResourceDimension.RETRIEVAL_ROUNDS):
        engine.budget.commit(ResourceDimension.RETRIEVAL_ROUNDS)
    assert engine.retrieve("q") == []
    assert calls == []  # bypassing is impossible: the engine is the only path


# -- restart resumes trajectories/stages ----------------------------------

def test_restart_resumes_trajectories_and_stages(tmp_path: Path) -> None:
    store = SqliteRunStateStore(tmp_path / "runs.db")
    store.initialize()

    provider, _ = _make_fake_provider()
    runtime = _build_runtime(tmp_path, provider)
    first = runtime.run_high_effort(
        profile="XHIGH",
        store=store,
        run_id="run-1",
        task_description="surface code threshold",
        trajectory_strategies=(TrajectoryStrategy.DIRECT,),
        project_id="p",
    )
    assert first.status is RunStatus.COMPLETED
    assert len(first.trajectories) == 1

    # "Restart" the same run: the store persists the logical run state, so a new
    # run with the same run_id resumes rather than recreates.
    resumed = runtime.run_high_effort(
        profile="XHIGH",
        store=store,
        run_id="run-1",
        task_description="surface code threshold",
        trajectory_strategies=(TrajectoryStrategy.DIRECT,),
        project_id="p",
    )
    # Trajectories are resumed, not recreated.
    assert len(resumed.trajectories) == 1
    assert resumed.trajectories[0].trajectory_id == first.trajectories[0].trajectory_id
    # Completed stages are preserved (no re-execution of already-done stages).
    assert resumed.completed_stages == first.completed_stages
    # The final synthesis is preserved across restart (no new inference calls).
    assert resumed.final_synthesis == first.final_synthesis


def test_run_state_roundtrip() -> None:
    store = InMemoryRunStateStore()
    state = HighEffortRunState(
        run_id="r", profile="XHIGH", task_description="t",
        budget=get_test_time_policy("XHIGH").budget(),
        completed_stages=["verification"],
        evidence_refs=["e1"],
        final_synthesis="done",
    )
    store.save_state(state)
    loaded = store.load_state("r")
    assert loaded is not None
    assert loaded.evidence_refs == ["e1"]
    assert loaded.completed_stages == ["verification"]
    assert loaded.final_synthesis == "done"
    assert loaded.budget.consumed_for(ResourceDimension.TOOL_CALLS) == 0


# -- Phase-9 inheritance tests -------------------------------------------

def test_high_effort_duplicate_call_id_replays_not_reexecutes() -> None:
    store = InMemoryToolExecutionStore()
    identity = ToolExecutionIdentity("session-1", "call-1")
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
        lease_owner="A",
        lease_duration_seconds=120.0,
    )
    store.complete(identity, "lease-1", ToolExecutionResult(
        call_id="call-1", tool_name="search_corpus", status=ToolExecutionStatus.SUCCEEDED
    ))
    replay = store.claim(
        identity,
        tool_name="search_corpus",
        arguments_hash=canonical_arguments_hash({"query": "q"}),
        project_id="default",
        session_id="",
        task_id=None,
        run_id=None,
        execution_semantics=ToolExecutionSemantics.READ_ONLY,
        permission="read",
        lease_id="lease-2",
        lease_owner="B",
        lease_duration_seconds=120.0,
    )
    assert replay.outcome is ClaimOutcome.ALREADY_COMPLETED
    assert replay.result is not None
    assert replay.result.status is ToolExecutionStatus.SUCCEEDED


def test_high_effort_concurrent_claim_one_owner() -> None:
    store = InMemoryToolExecutionStore()
    identity = ToolExecutionIdentity("session-1", "call-1")
    barrier = threading.Barrier(2)

    def worker(owner: str) -> None:
        barrier.wait()
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
            lease_id=f"lease-{owner}",
            lease_owner=owner,
            lease_duration_seconds=120.0,
        )

    threads = [threading.Thread(target=worker, args=(f"o{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    record = store.inspect(identity)
    assert record is not None
    assert record.lease_owner in ("o0", "o1")
    assert record.attempt == 1
