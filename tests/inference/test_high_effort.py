"""Phase 10 high-effort execution + Phase-9 inheritance tests."""

from __future__ import annotations

import threading
from typing import Any

from qwen_research.domain.test_time import (
    CritiqueAction,
    CritiqueIssue,
    CritiqueRequest,
    CritiqueResult,
    ResearchSynthesisInput,
    ResourceDimension,
    RunStatus,
    TrajectoryStrategy,
)
from qwen_research.research.budget_store import SqliteBudgetStore
from qwen_research.research.high_effort import (
    HighEffortContext,
    perform_critique,
    reallocate_after_signal,
    run_high_effort,
    run_trajectory,
)
from qwen_research.research.scheduler import BudgetSignal
from qwen_research.research.tool_execution import (
    ClaimOutcome,
    InMemoryToolExecutionStore,
    ToolExecutionIdentity,
    ToolExecutionSemantics,
    canonical_arguments_hash,
)
from qwen_research.research.tool_loop import ToolExecutionResult, ToolExecutionStatus


def _xhigh_stages(ctx: HighEffortContext) -> ResearchSynthesisInput:
    """A deterministic XHIGH trace: retrieval → verification → contradiction →
    adaptive reallocation → retrieval 2 → computation → trajectories → critique
    → re-verification → synthesis. Every step consumes budget."""
    events = ctx.events
    events.append("retrieval_round_1")
    ctx.spend(ResourceDimension.RETRIEVAL_ROUNDS)
    ctx.spend(ResourceDimension.INFERENCE_CALLS)
    ctx.spend(ResourceDimension.TOOL_CALLS)

    events.append("verification")
    ctx.spend(ResourceDimension.VERIFICATION_ROUNDS)

    events.append("contradiction_found")
    reallocate_after_signal(
        ctx, BudgetSignal(ResourceDimension.VERIFICATION_ROUNDS, "strong", "contradiction")
    )

    events.append("retrieval_round_2")
    ctx.spend(ResourceDimension.RETRIEVAL_ROUNDS)

    events.append("computation")
    ctx.spend(ResourceDimension.COMPUTATION_ROUNDS)

    for trajectory in ctx.trajectories:
        run_trajectory(
            ctx, trajectory, inference_calls=1, tool_calls=2, retrieval_rounds=1
        )

    critique = perform_critique(
        ctx,
        CritiqueRequest(draft="draft", claims=("c1",)),
        critique=lambda req: CritiqueResult(
            issues=(
                CritiqueIssue(
                    severity="major", description="unsupported claim", claim_refs=("c1",)
                ),
            ),
            recommended_action=CritiqueAction.VERIFY_MORE,
        ),
    )
    assert critique.recommended_action is CritiqueAction.VERIFY_MORE

    events.append("re_verification")
    ctx.spend(ResourceDimension.VERIFICATION_ROUNDS)

    events.append("final_synthesis")
    ctx.spend(ResourceDimension.SYNTHESIS_PASSES)
    return ResearchSynthesisInput(claims=("c1",), unresolved_questions=())


def test_xhigh_trace_consumes_within_budget() -> None:
    result = run_high_effort(
        profile_name="XHIGH",
        task_description="surface-code threshold",
        trajectory_strategies=(TrajectoryStrategy.DIRECT, TrajectoryStrategy.COUNTERARGUMENT),
        stages=_xhigh_stages,
    )
    assert result.status is RunStatus.COMPLETED
    summary = result.budget_summary
    # consumed <= allocated for every dimension.
    for dimension, allocated in summary["allocated"].items():
        assert summary["consumed"][dimension] <= allocated, dimension
    # Two trajectories admitted (XHIGH allows 3).
    assert len(result.trajectories) == 2
    assert len(result.reallocation_decisions) >= 1
    assert result.synthesis_input is not None


def test_extreme_trace_within_budget() -> None:
    def stages(ctx: HighEffortContext) -> ResearchSynthesisInput:
        for _ in range(3):
            ctx.spend(ResourceDimension.RETRIEVAL_ROUNDS)
        for _ in range(2):
            ctx.spend(ResourceDimension.VERIFICATION_ROUNDS)
        ctx.spend(ResourceDimension.COMPUTATION_ROUNDS)
        for trajectory in ctx.trajectories:
            run_trajectory(ctx, trajectory, inference_calls=1, tool_calls=1, retrieval_rounds=1)
        ctx.spend(ResourceDimension.CRITIQUE_ROUNDS)
        ctx.spend(ResourceDimension.SYNTHESIS_PASSES)
        return ResearchSynthesisInput()

    result = run_high_effort(
        profile_name="EXTREME",
        trajectory_strategies=(TrajectoryStrategy.DIRECT, TrajectoryStrategy.DATA_DRIVEN),
        stages=stages,
    )
    assert result.status is RunStatus.COMPLETED
    for dimension, allocated in result.budget_summary["allocated"].items():
        assert result.budget_summary["consumed"][dimension] <= allocated, dimension


def test_trajectory_budget_never_exceeded() -> None:
    # EXTREME allows 5 trajectories; request 6 → 5 admitted, 6th denied.
    result = run_high_effort(
        profile_name="EXTREME",
        trajectory_strategies=(TrajectoryStrategy.DIRECT,) * 6,
        stages=lambda ctx: ResearchSynthesisInput(),
    )
    assert len(result.trajectories) == 5
    consumed_traj = result.budget_summary["consumed"][ResourceDimension.TRAJECTORIES.value]
    assert consumed_traj == 5


def test_budget_exhaustion_status() -> None:
    def stages(ctx: HighEffortContext) -> ResearchSynthesisInput:
        # Exhaust every dimension.
        for dimension in list(ctx.budget.allocated):
            while ctx.budget.can_afford(dimension):
                ctx.budget.commit(dimension)
        return ResearchSynthesisInput()

    result = run_high_effort(profile_name="FAST", stages=stages)
    assert result.status is RunStatus.BUDGET_EXHAUSTED


def test_restart_preserves_consumed_budget(tmp_path: Any) -> None:
    store = SqliteBudgetStore(tmp_path / "budgets.db")
    store.initialize()

    def stages(ctx: HighEffortContext) -> ResearchSynthesisInput:
        ctx.spend(ResourceDimension.TOOL_CALLS, 5)
        return ResearchSynthesisInput()

    first = run_high_effort(profile_name="XHIGH", store=store, run_id="run-1", stages=stages)
    consumed_tools_first = first.budget_summary["consumed"]["tool_calls"]
    assert consumed_tools_first == 5

    # "Restart" the same run: consumed is preserved, not reset.
    resumed = run_high_effort(profile_name="XHIGH", store=store, run_id="run-1", stages=stages)
    consumed_tools_resumed = resumed.budget_summary["consumed"]["tool_calls"]
    assert consumed_tools_resumed >= 5  # never reset to 0


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
    # A high-effort "retry" of the same identity replays, never re-executes.
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

    # Exactly one owner: the second claim must be ALREADY_CLAIMED (verified by
    # inspecting the record's single lease owner).
    record = store.inspect(identity)
    assert record is not None
    assert record.lease_owner in ("o0", "o1")
    assert record.attempt == 1  # only one physical claim
