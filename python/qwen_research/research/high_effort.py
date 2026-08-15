"""Bounded high-effort research execution (Phase 10).

Coordinates the workflow dimensions that FAST/NORMAL/DEEP/XHIGH/EXTREME scale:
retrieval, verification, computation, trajectories, critique, and synthesis
passes — each governed by the provider-neutral :class:`TestTimeComputeBudget`
and its per-dimension meters. This is a *resource-allocation* layer, not a
privilege-escalation layer: XHIGH/EXTREME never grant more permissions and never
store hidden reasoning.

Restart-safe: a budget loaded from a :class:`BudgetStore` resumes with its
consumed counters intact (never reset to zero).
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from typing import Any

from qwen_research.common.ids import new_id
from qwen_research.common.serialization import serializable
from qwen_research.domain.test_time import (
    CritiqueAction,
    CritiqueRequest,
    CritiqueResult,
    ResearchSynthesisInput,
    ResearchTrajectory,
    ResourceDimension,
    RunStatus,
    TestTimeComputeBudget,
    TestTimeComputePolicy,
    TrajectoryStrategy,
    get_test_time_policy,
)
from qwen_research.research.budget_store import BudgetStore
from qwen_research.research.scheduler import (
    BudgetMeter,
    BudgetSignal,
    TestTimeScheduler,
)


@dataclasses.dataclass
class HighEffortContext:
    """Mutable state handed to stage callbacks (no hidden reasoning)."""

    profile: TestTimeComputePolicy
    budget: TestTimeComputeBudget
    scheduler: TestTimeScheduler
    meters: dict[ResourceDimension, BudgetMeter]
    trajectories: list[ResearchTrajectory]
    critique_results: list[CritiqueResult]
    signals: list[BudgetSignal]
    events: list[str]
    started_at: float

    def reserve(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        return self.meters[dimension].reserve(amount)

    def commit(self, dimension: ResourceDimension, amount: float = 1.0) -> None:
        self.meters[dimension].commit(amount)

    def spend(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        """Reserve-and-commit a unit of *dimension* in one step."""
        if not self.reserve(dimension, amount):
            return False
        self.commit(dimension, amount)
        return True

    def wall_time_exhausted(self) -> bool:
        elapsed = time.monotonic() - self.started_at
        return elapsed >= self.profile.max_wall_time_seconds

    def should_continue(self) -> bool:
        return not (self.wall_time_exhausted() or self.budget.all_exhausted())


@serializable
@dataclasses.dataclass(frozen=True)
class HighEffortResult:
    """The outcome of a high-effort run."""

    status: RunStatus
    profile: str
    budget_summary: dict[str, Any]
    trajectories: tuple[ResearchTrajectory, ...] = ()
    critique_results: tuple[CritiqueResult, ...] = ()
    synthesis_input: ResearchSynthesisInput | None = None
    reallocation_decisions: tuple[Any, ...] = ()
    error: str | None = None


def run_high_effort(
    *,
    profile_name: str,
    store: BudgetStore | None = None,
    run_id: str = "",
    task_description: str = "",
    stages: Callable[[HighEffortContext], ResearchSynthesisInput | None] | None = None,
    trajectory_strategies: tuple[TrajectoryStrategy, ...] = (),
) -> HighEffortResult:
    """Run a bounded high-effort research execution.

    ``stages`` is an injected callback that performs the actual workflow work
    (retrieval/verification/computation/critique) against the provided context;
    each stage must ``reserve``/``commit`` budget. When ``store`` is provided the
    budget is loaded (resume) or allocated (fresh) and persisted after each
    stage.
    """
    profile = get_test_time_policy(profile_name)
    run_id = run_id or new_id("run")

    # Restart-safe: resume an existing budget, else allocate a fresh one.
    budget = store.load(run_id) if store is not None else None
    if budget is None:
        budget = profile.budget()

    scheduler = TestTimeScheduler(budget)
    meters = {d: BudgetMeter(budget, d) for d in budget.allocated}
    context = HighEffortContext(
        profile=profile,
        budget=budget,
        scheduler=scheduler,
        meters=meters,
        trajectories=[],
        critique_results=[],
        signals=[],
        events=[task_description],
        started_at=time.monotonic(),
    )

    def _persist() -> None:
        if store is not None:
            store.save(run_id, budget)

    # Admit bounded, distinct trajectories (never beyond the global ceiling).
    for strategy in trajectory_strategies:
        if not context.spend(ResourceDimension.TRAJECTORIES):
            context.events.append(f"trajectory {strategy.value} not admitted: budget")
            break
        context.trajectories.append(
            ResearchTrajectory.create(strategy, task_description)
        )

    try:
        synthesis = stages(context) if stages is not None else None
    except Exception as exc:  # noqa: BLE001 — normalize run failure
        _persist()
        return HighEffortResult(
            status=RunStatus.FAILED,
            profile=profile_name,
            budget_summary=budget.summary(),
            trajectories=tuple(context.trajectories),
            critique_results=tuple(context.critique_results),
            reallocation_decisions=scheduler.decisions,
            error=f"{type(exc).__name__}: {exc}",
        )

    _persist()

    if context.wall_time_exhausted():
        status = RunStatus.TIME_LIMIT
    elif budget.all_exhausted():
        status = RunStatus.BUDGET_EXHAUSTED
    elif synthesis is None:
        status = RunStatus.SYNTHESIS_REQUIRED
    else:
        status = RunStatus.COMPLETED

    return HighEffortResult(
        status=status,
        profile=profile_name,
        budget_summary=budget.summary(),
        trajectories=tuple(context.trajectories),
        critique_results=tuple(context.critique_results),
        synthesis_input=synthesis,
        reallocation_decisions=scheduler.decisions,
    )


def run_trajectory(
    context: HighEffortContext,
    trajectory: ResearchTrajectory,
    *,
    inference_calls: int = 1,
    tool_calls: int = 0,
    retrieval_rounds: int = 0,
) -> ResearchTrajectory:
    """Execute one trajectory's bounded work against the shared global budget.

    Every resource is reserved/committed against the global ceiling — a
    trajectory can never exceed it, and consumption is permanent within the run.
    """
    for _ in range(inference_calls):
        if not context.spend(ResourceDimension.INFERENCE_CALLS):
            break
        context.spend(ResourceDimension.INFERENCE_TURNS)
    for _ in range(tool_calls):
        if not context.spend(ResourceDimension.TOOL_CALLS):
            break
    for _ in range(retrieval_rounds):
        if not context.spend(ResourceDimension.RETRIEVAL_ROUNDS):
            break
    return dataclasses.replace(trajectory, status="completed")


def perform_critique(
    context: HighEffortContext,
    request: CritiqueRequest,
    *,
    critique: Callable[[CritiqueRequest], CritiqueResult],
) -> CritiqueResult:
    """Run a bounded critique pass; a non-trivial action consumes budget."""
    if not context.spend(ResourceDimension.CRITIQUE_ROUNDS):
        return CritiqueResult(
            recommended_action=CritiqueAction.NO_ACTION,
            recommendation_reason="critique budget exhausted",
        )
    result = critique(request)
    context.critique_results.append(result)
    if result.recommended_action is not CritiqueAction.NO_ACTION:
        _consume_critique_action(context, result.recommended_action)
    return result


def _consume_critique_action(context: HighEffortContext, action: CritiqueAction) -> None:
    dimension = {
        CritiqueAction.RETRIEVE_MORE: ResourceDimension.RETRIEVAL_ROUNDS,
        CritiqueAction.VERIFY_MORE: ResourceDimension.VERIFICATION_ROUNDS,
        CritiqueAction.COMPUTE_MORE: ResourceDimension.COMPUTATION_ROUNDS,
        CritiqueAction.REWRITE: ResourceDimension.SYNTHESIS_PASSES,
        CritiqueAction.REJECT_DRAFT: ResourceDimension.SYNTHESIS_PASSES,
    }.get(action)
    if dimension is not None:
        context.spend(dimension)


def reallocate_after_signal(context: HighEffortContext, signal: BudgetSignal) -> None:
    """Apply an adaptive reallocation and record the signal for observability."""
    context.signals.append(signal)
    context.scheduler.apply_signal(signal)
