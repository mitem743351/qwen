"""Bounded high-effort research execution (Phase 10.1).

A **real** engine that drives the Research Runtime, rather than a callback that
manually spends counters. The engine owns the global
:class:`TestTimeComputeBudget` and consumes it *automatically* around each real
runtime call (inference, tool loop, retrieval, verification, computation), so
callers cannot bypass the budget. Wall-time is checked before every operation —
not after the run finishes. Logical run state (trajectories, stages, budget) is
persisted and resumed across restarts.

XHIGH/EXTREME mean *more bounded useful work*, never more permissions or
hidden-reasoning storage.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any

from qwen_research.common.ids import TaskId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.domain.errors import UnsupportedOperationError
from qwen_research.domain.inference import (
    InferenceRequest,
    InferenceResult,
    Message,
    MessageRole,
)
from qwen_research.domain.test_time import (
    CritiqueAction,
    CritiqueIssue,
    CritiqueResult,
    HighEffortRunState,
    ResearchSynthesisInput,
    ResearchTrajectory,
    ResourceDimension,
    RunStatus,
    TestTimeComputeBudget,
    TestTimeComputePolicy,
    TrajectoryStrategy,
    get_test_time_policy,
    trajectory_query_set,
)
from qwen_research.research.budget_store import RunStateStore
from qwen_research.research.scheduler import (
    BudgetMeter,
    BudgetSignal,
    TestTimeScheduler,
    make_budget_meters,
)
from qwen_research.retrieval.models import SearchOptions


class _BudgetExhaustedError(Exception):
    """Internal signal: a required budget dimension is exhausted mid-run."""


_CRITIQUE_SYSTEM = (
    "You are a rigorous research critic. Identify unsupported claims, missing "
    "evidence, contradictions, scope errors, numerical errors, citation "
    "mismatches, overclaiming, and incomplete answers in the draft. Reply with "
    "the single most severe issue found, or 'none' if the draft is sound."
)

_SYNTHESIS_SYSTEM = (
    "You are a rigorous research synthesis assistant. Ground every claim in the "
    "provided evidence and clearly distinguish established findings, "
    "contradictions, and open questions. Do not fabricate evidence."
)


class HighEffortEngine:
    """Drives a bounded high-effort run against a real Research Runtime.

    Every operation checks wall-time and budget **before** executing and commits
    consumption **after**; the engine is the only path to the runtime during the
    run, so the global budget is authoritative.
    """

    def __init__(
        self,
        runtime: Any,
        profile_name: str,
        state: HighEffortRunState,
        *,
        project_id: str = "default",
    ) -> None:
        self.runtime = runtime
        self.profile: TestTimeComputePolicy = get_test_time_policy(profile_name)
        self.state = state
        self.budget: TestTimeComputeBudget = state.budget
        self.scheduler = TestTimeScheduler(self.budget)
        self.meters: dict[ResourceDimension, BudgetMeter] = make_budget_meters(self.budget)
        self.project_id = project_id
        self.task_reference = TaskId(new_id("task"))
        self.started_at = time.monotonic()
        self.events: list[str] = list(state.completed_stages)

    # -- budget + wall-time -------------------------------------------------

    def wall_time_exhausted(self) -> bool:
        return (time.monotonic() - self.started_at) >= self.profile.max_wall_time_seconds

    def should_continue(self) -> bool:
        return not (self.wall_time_exhausted() or self.budget.all_exhausted())

    def can(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        return self.should_continue() and self.meters[dimension].remaining() >= amount

    def spend(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        """Atomically reserve + commit one unit of *dimension*."""
        meter = self.meters[dimension]
        if not meter.reserve(amount):
            return False
        meter.commit(amount)
        return True

    # -- real runtime operations (auto-consuming) --------------------------

    def invoke(self, messages: tuple[Message, ...]) -> InferenceResult:
        """Invoke inference; consumes INFERENCE_CALLS/TURNS/TOKENS."""
        if not self.can(ResourceDimension.INFERENCE_CALLS):
            raise _BudgetExhaustedError("inference budget exhausted")
        self.spend(ResourceDimension.INFERENCE_CALLS)
        self.spend(ResourceDimension.INFERENCE_TURNS)
        policy = self.profile.inference_policy()
        request = InferenceRequest(
            task_reference=self.task_reference,
            inference_policy=policy,
            messages=messages,
        )
        result: InferenceResult = self.runtime.invoke_inference(request)
        usage = result.usage or {}
        self.meters[ResourceDimension.TOKENS].commit(float(usage.get("total_tokens", 0)))
        return result

    def retrieve(self, query: str, *, limit: int | None = None) -> list[str]:
        """One retrieval round; consumes RETRIEVAL_ROUNDS + RETRIEVAL_CANDIDATES."""
        if not self.can(ResourceDimension.RETRIEVAL_ROUNDS):
            return []
        self.spend(ResourceDimension.RETRIEVAL_ROUNDS)
        cap = limit or int(self.profile.max_retrieval_candidates)
        result = self.runtime.search_corpus(query, SearchOptions(limit=cap))
        chunk_ids = [c.chunk_id for c in result.chunks]
        for _ in chunk_ids:
            if not self.spend(ResourceDimension.RETRIEVAL_CANDIDATES):
                break
        return chunk_ids

    def verify(self, claim_text: str) -> str | None:
        """Create + verify a claim; consumes VERIFICATION_ROUNDS. Returns report id."""
        if not self.can(ResourceDimension.VERIFICATION_ROUNDS):
            return None
        claim = self.runtime.create_claim(self.project_id, claim_text)
        self.state.claims.append(claim.claim_id)
        self.spend(ResourceDimension.VERIFICATION_ROUNDS)
        report = self.runtime.verify_claim(self.project_id, claim.claim_id)
        report_id: str = report.report_id
        self.state.verification_refs.append(report_id)
        return report_id

    def contradictions(self) -> list[str]:
        """Detect contradictions; consumes VERIFICATION_ROUNDS. Returns ids."""
        if not self.can(ResourceDimension.VERIFICATION_ROUNDS):
            return []
        self.spend(ResourceDimension.VERIFICATION_ROUNDS)
        found = self.runtime.get_contradictions(self.project_id)
        ids = [c.contradiction_id for c in found]
        self.state.contradictions.extend(ids)
        return ids

    def compute(self, dataset_ref: Any) -> str | None:
        """Run a bounded computation; consumes COMPUTATION_ROUNDS."""
        if not self.can(ResourceDimension.COMPUTATION_ROUNDS):
            return None
        self.spend(ResourceDimension.COMPUTATION_ROUNDS)
        from qwen_research.computation.models import ComputationOperation

        result = self.runtime.run_analysis(
            self.project_id, (dataset_ref,), ComputationOperation.SUMMARIZE
        )
        computation_id: str = result.computation_id
        self.state.computation_refs.append(computation_id)
        return computation_id

    def critique(self, draft: str, *, claims: tuple[str, ...] = ()) -> CritiqueResult:
        """Model-backed critique; consumes CRITIQUE_ROUNDS + inference."""
        if not self.can(ResourceDimension.CRITIQUE_ROUNDS):
            return CritiqueResult(
                recommended_action=CritiqueAction.NO_ACTION,
                recommendation_reason="critique budget exhausted",
            )
        self.spend(ResourceDimension.CRITIQUE_ROUNDS)
        result = self.invoke(
            (
                Message(role=MessageRole.SYSTEM, content=_CRITIQUE_SYSTEM),
                Message(
                    role=MessageRole.USER,
                    content=f"Draft: {draft}\nClaims: {', '.join(claims) or '(none)'}",
                ),
            )
        )
        parsed = _parse_critique(result.content)
        self.state.critique_results.append(parsed)
        if parsed.recommended_action is not CritiqueAction.NO_ACTION:
            self._consume_critique_action(parsed.recommended_action)
        return parsed

    def synthesize(self, synth_input: ResearchSynthesisInput) -> InferenceResult:
        """Final evidence-aware synthesis; consumes SYNTHESIS_PASSES + inference."""
        if not self.can(ResourceDimension.SYNTHESIS_PASSES):
            raise _BudgetExhaustedError("synthesis budget exhausted")
        self.spend(ResourceDimension.SYNTHESIS_PASSES)
        user = (
            f"Objective: {self.state.task_description}\n"
            f"Evidence refs: {', '.join(synth_input.evidence_refs) or '(none)'}\n"
            f"Verified claims: {', '.join(self.state.claims) or '(none)'}\n"
            f"Contradictions: {', '.join(self.state.contradictions) or '(none)'}\n"
            f"Unresolved: {', '.join(synth_input.unresolved_questions) or '(none)'}\n"
            "Produce a grounded synthesis."
        )
        return self.invoke(
            (
                Message(role=MessageRole.SYSTEM, content=_SYNTHESIS_SYSTEM),
                Message(role=MessageRole.USER, content=user),
            )
        )

    def run_tool_loop(self, request: InferenceRequest) -> Any:
        """Run the Phase-9 tool loop; auto-consumes TOOL_CALLS + inference."""
        if not self.can(ResourceDimension.TOOL_CALLS):
            raise _BudgetExhaustedError("tool budget exhausted")
        result = self.runtime.run_tool_loop(request, project_id=self.project_id)
        self.spend(ResourceDimension.TOOL_CALLS, float(result.accounting.tool_calls))
        self.spend(ResourceDimension.INFERENCE_CALLS, float(result.accounting.inference_calls))
        return result

    # -- helpers -----------------------------------------------------------

    def _consume_critique_action(self, action: CritiqueAction) -> None:
        dimension = {
            CritiqueAction.RETRIEVE_MORE: ResourceDimension.RETRIEVAL_ROUNDS,
            CritiqueAction.VERIFY_MORE: ResourceDimension.VERIFICATION_ROUNDS,
            CritiqueAction.COMPUTE_MORE: ResourceDimension.COMPUTATION_ROUNDS,
            CritiqueAction.REWRITE: ResourceDimension.SYNTHESIS_PASSES,
            CritiqueAction.REJECT_DRAFT: ResourceDimension.SYNTHESIS_PASSES,
        }.get(action)
        if dimension is not None:
            self.spend(dimension)

    def reallocate_after_signal(self, signal: BudgetSignal) -> None:
        self.scheduler.apply_signal(signal)


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
    final_synthesis: str = ""
    reallocation_decisions: tuple[Any, ...] = ()
    completed_stages: tuple[str, ...] = ()
    error: str | None = None


def run_high_effort(
    runtime: Any,
    *,
    profile_name: str,
    store: RunStateStore | None = None,
    run_id: str = "",
    task_description: str = "",
    trajectory_strategies: tuple[TrajectoryStrategy, ...] = (),
    project_id: str = "default",
    dataset_ref: Any = None,
    tool_request: InferenceRequest | None = None,
) -> HighEffortResult:
    """Run a bounded high-effort research execution against a real runtime.

    ``store`` (optional) persists the full logical run state; a restart resumes
    trajectories/stages and budget consumption rather than recreating them.
    """
    run_id = run_id or new_id("run")

    state = store.load_state(run_id) if store is not None else None
    if state is None:
        state = HighEffortRunState(
            run_id=run_id,
            profile=profile_name,
            task_description=task_description,
            budget=get_test_time_policy(profile_name).budget(),
        )

    engine = HighEffortEngine(runtime, profile_name, state, project_id=project_id)

    try:
        _execute(engine, trajectory_strategies, dataset_ref=dataset_ref, tool_request=tool_request)
    except _BudgetExhaustedError as exc:
        _persist(store, state)
        return _finalize(engine, state, error=f"{exc}")
    except Exception as exc:  # noqa: BLE001 — normalize run failure
        _persist(store, state)
        return HighEffortResult(
            status=RunStatus.FAILED,
            profile=profile_name,
            budget_summary=state.budget.summary(),
            trajectories=tuple(state.trajectories),
            critique_results=tuple(state.critique_results),
            reallocation_decisions=engine.scheduler.decisions,
            completed_stages=tuple(state.completed_stages),
            error=f"{type(exc).__name__}: {exc}",
        )

    _persist(store, state)
    return _finalize(engine, state)


def _persist(store: RunStateStore | None, state: HighEffortRunState) -> None:
    if store is not None:
        store.save_state(state)


def _execute(
    engine: HighEffortEngine,
    trajectory_strategies: tuple[TrajectoryStrategy, ...],
    *,
    dataset_ref: Any,
    tool_request: InferenceRequest | None,
) -> None:
    state = engine.state

    # 1. Trajectories (admit + retrieve); resume skips already-done strategies.
    for strategy in trajectory_strategies:
        if any(t.strategy is strategy for t in state.trajectories):
            continue
        if not engine.should_continue() or not engine.spend(ResourceDimension.TRAJECTORIES):
            break
        trajectory = ResearchTrajectory.create(strategy, state.task_description)
        qset = trajectory_query_set(strategy, state.task_description)
        evidence: list[str] = []
        for query in qset.all_queries():
            if not engine.should_continue():
                break
            evidence.extend(engine.retrieve(query))
        state.evidence_refs.extend(evidence)
        state.trajectories.append(
            dataclasses.replace(trajectory, evidence_refs=tuple(evidence), status="completed")
        )

    # 2. Verification (create + verify a claim; resume skips if already done).
    if (
        "verification" not in state.completed_stages
        and engine.should_continue()
        and engine.can(ResourceDimension.VERIFICATION_ROUNDS)
    ):
        try:
            engine.verify(state.task_description or "research objective")
            state.completed_stages.append("verification")
        except UnsupportedOperationError:
            pass  # verification subsystem not configured → skip

    # 3. Contradiction search (adaptive escalation if contradictions found).
    if (
        "contradictions" not in state.completed_stages
        and engine.should_continue()
        and engine.can(ResourceDimension.VERIFICATION_ROUNDS)
    ):
        try:
            found = engine.contradictions()
            state.completed_stages.append("contradictions")
            if found:
                engine.reallocate_after_signal(
                    BudgetSignal(
                        ResourceDimension.VERIFICATION_ROUNDS, "strong", "contradiction found"
                    )
                )
        except UnsupportedOperationError:
            pass

    # 4. Computation (optional).
    if (
        dataset_ref is not None
        and "computation" not in state.completed_stages
        and engine.should_continue()
        and engine.can(ResourceDimension.COMPUTATION_ROUNDS)
    ):
        try:
            engine.compute(dataset_ref)
            state.completed_stages.append("computation")
        except UnsupportedOperationError:
            pass

    # 5. Tool loop (optional; the tool loop's own accounting drives consumption).
    if (
        tool_request is not None
        and "tool_loop" not in state.completed_stages
        and engine.should_continue()
    ):
        engine.run_tool_loop(tool_request)
        state.completed_stages.append("tool_loop")

    # 6. Critique (model-backed; consumes budget).
    if (
        "critique" not in state.completed_stages
        and engine.should_continue()
        and engine.can(ResourceDimension.CRITIQUE_ROUNDS)
    ):
        engine.critique(state.task_description, claims=tuple(state.claims))
        state.completed_stages.append("critique")

    # 7. Final synthesis (resume skips if already done).
    if "synthesis" not in state.completed_stages and engine.can(ResourceDimension.SYNTHESIS_PASSES):
        synth_input = _synthesis_input(state)
        result = engine.synthesize(synth_input)
        state.completed_stages.append("synthesis")
        state.final_synthesis = result.content


def _synthesis_input(state: HighEffortRunState) -> ResearchSynthesisInput:
    return ResearchSynthesisInput(
        claims=tuple(state.claims),
        evidence_refs=tuple(state.evidence_refs),
        verification_refs=tuple(state.verification_refs),
        contradictions=tuple(state.contradictions),
        computations=tuple(state.computation_refs),
        trajectory_findings=tuple(t.trajectory_id for t in state.trajectories),
        critique_findings=tuple(
            f"{i.description}" for c in state.critique_results for i in c.issues
        ),
        unresolved_questions=(),
    )


def _completion_met(state: HighEffortRunState) -> bool:
    """Completion requires real evidence and real verification coverage."""
    return bool(state.evidence_refs) and bool(state.verification_refs)


def _finalize(
    engine: HighEffortEngine, state: HighEffortRunState, *, error: str | None = None
) -> HighEffortResult:
    if error is not None:
        status = RunStatus.BUDGET_EXHAUSTED
    elif engine.wall_time_exhausted():
        status = RunStatus.TIME_LIMIT
    elif engine.budget.all_exhausted():
        status = RunStatus.BUDGET_EXHAUSTED
    elif _completion_met(state) and "synthesis" in state.completed_stages:
        status = RunStatus.COMPLETED
    elif "synthesis" in state.completed_stages:
        status = RunStatus.PARTIAL
    else:
        status = RunStatus.SYNTHESIS_REQUIRED

    return HighEffortResult(
        status=status,
        profile=state.profile,
        budget_summary=state.budget.summary(),
        trajectories=tuple(state.trajectories),
        critique_results=tuple(state.critique_results),
        synthesis_input=_synthesis_input(state),
        final_synthesis=state.final_synthesis,
        reallocation_decisions=engine.scheduler.decisions,
        completed_stages=tuple(state.completed_stages),
        error=error,
    )


def _parse_critique(content: str) -> CritiqueResult:
    """Deterministic, model-output-driven critique parsing (no hidden state)."""
    text = (content or "").strip().lower()
    if not text or "none" in text:
        return CritiqueResult()
    issues: list[CritiqueIssue] = []
    action = CritiqueAction.NO_ACTION
    if "unsupported claim" in text:
        issues.append(CritiqueIssue(severity="major", description="unsupported claim"))
        action = CritiqueAction.VERIFY_MORE
    elif "insufficient evidence" in text:
        issues.append(CritiqueIssue(severity="warning", description="insufficient evidence"))
        action = CritiqueAction.RETRIEVE_MORE
    elif "contradiction" in text:
        issues.append(CritiqueIssue(severity="major", description="contradiction"))
        action = CritiqueAction.VERIFY_MORE
    else:
        issues.append(CritiqueIssue(severity="warning", description=content.strip()))
    return CritiqueResult(issues=tuple(issues), recommended_action=action)
