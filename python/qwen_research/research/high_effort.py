"""Bounded high-effort research execution (Phase 10.2).

A **real** engine that drives the Research Runtime and *enforces* its resource,
state, deadline, and restart guarantees:

- **Admission vs accounting** are separate: every expensive child operation is
  admitted (budget + deadline) *before* it runs, receives a bounded child
  limit derived from the remaining global budget/deadline, and commits actual
  consumption *after*. Post-hoc clamping is never used to hide overruns.
- **Absolute wall-clock deadline** is persisted and restored; a restart resumes
  with the remaining time, never a fresh window.
- **Checkpoint after every durable transition** — a completed stage becomes
  durable before the next stage depends on it.
- **Trajectory state machine** — an early-stopped trajectory is never marked
  COMPLETED.
- **Draft → critique → real action → revision → final critique → final
  verification** — critique operates on the actual draft and its actions
  perform real work.

XHIGH/EXTREME mean *more bounded useful work*, never more permissions or
hidden-reasoning storage. The frozen Phase-9 execution guarantees are untouched.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any

from qwen_research.common.ids import TaskId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.domain.errors import UnsupportedOperationError
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    Message,
    MessageRole,
)
from qwen_research.domain.test_time import (
    CritiqueAction,
    CritiqueIssue,
    CritiqueResult,
    DraftStatus,
    HighEffortRunState,
    ResearchSynthesisInput,
    ResearchTrajectory,
    ResourceDimension,
    RunStatus,
    TestTimeComputeBudget,
    TestTimeComputePolicy,
    TrajectoryStatus,
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

_REWRITE_SYSTEM = (
    "You are a rigorous research reviser. Revise the draft to resolve the "
    "critic's most severe issue, grounding every claim in the provided evidence. "
    "Do not fabricate evidence."
)


class HighEffortEngine:
    """Drives a bounded high-effort run against a real Research Runtime.

    The engine is the **authoritative** owner of the logical run budget and
    deadline; every child operation passes through admission (budget + deadline)
    before execution and commits consumption after.
    """

    def __init__(
        self,
        runtime: Any,
        profile_name: str,
        state: HighEffortRunState,
        *,
        project_id: str = "default",
        store: RunStateStore | None = None,
    ) -> None:
        self.runtime = runtime
        self.profile: TestTimeComputePolicy = get_test_time_policy(profile_name)
        self.state = state
        self.budget: TestTimeComputeBudget = state.budget
        self.scheduler = TestTimeScheduler(self.budget)
        self.meters: dict[ResourceDimension, BudgetMeter] = make_budget_meters(self.budget)
        self.project_id = project_id
        self.task_reference = TaskId(new_id("task"))
        self.store = store
        # Absolute deadline: set once (fresh) and restored (resume).
        if state.deadline_at is None:
            state.deadline_at = time.time() + self.profile.max_wall_time_seconds
        self.events: list[str] = list(state.completed_stages)

    # -- deadline ----------------------------------------------------------

    def remaining_seconds(self) -> float:
        return max(0.0, (self.state.deadline_at or 0.0) - time.time())

    def deadline_exceeded(self) -> bool:
        return self.remaining_seconds() <= 0.0

    def should_continue(self) -> bool:
        return not (self.deadline_exceeded() or self.budget.all_exhausted())

    def can(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        return self.should_continue() and self.meters[dimension].remaining() >= amount

    # -- admission + accounting -------------------------------------------

    def reserve(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        return self.meters[dimension].reserve(amount)

    def commit(self, dimension: ResourceDimension, amount: float = 1.0) -> None:
        self.meters[dimension].commit(amount)

    def _admit(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        """Admit a unit of *dimension* (reserve, execute will follow, commit after)."""
        return self.reserve(dimension, amount)

    # -- real runtime operations (auto-consuming, admission-gated) ---------

    def invoke(self, messages: tuple[Message, ...]) -> InferenceResult:
        """Invoke inference with the remaining token budget as max_output_tokens.

        Admission consumes one inference call/turn; the request's
        ``max_output_tokens`` is bounded by the remaining token budget (never
        exceeding it), so the provider cannot be asked to overrun. Actual token
        usage is recorded; a provider overrun is flagged as a violation.
        """
        if not self.can(ResourceDimension.INFERENCE_CALLS):
            raise _BudgetExhaustedError("inference budget exhausted")
        self.reserve(ResourceDimension.INFERENCE_CALLS)
        self.reserve(ResourceDimension.INFERENCE_TURNS)
        policy = self.profile.inference_policy()
        remaining_tokens = int(self.meters[ResourceDimension.TOKENS].remaining())
        if remaining_tokens > 0:
            policy = InferencePolicy(
                **{**policy.__dict__, "max_output_tokens": remaining_tokens}
            )
        request = InferenceRequest(
            task_reference=self.task_reference,
            inference_policy=policy,
            messages=messages,
        )
        result: InferenceResult = self.runtime.invoke_inference(request)
        self.commit(ResourceDimension.INFERENCE_CALLS)
        self.commit(ResourceDimension.INFERENCE_TURNS)
        usage = result.usage or {}
        self._record_tokens(float(usage.get("total_tokens", 0)))
        return result

    def _record_tokens(self, actual: float) -> None:
        remaining = self.meters[ResourceDimension.TOKENS].remaining()
        if actual > remaining:
            self.state.violations.append(
                f"token overrun: provider used {actual} > remaining {remaining}"
            )
        self.commit(ResourceDimension.TOKENS, min(actual, remaining))

    def retrieve(self, query: str, *, limit: int | None = None) -> list[str]:
        """One retrieval round; candidate limit is bounded by remaining budget."""
        if not self.can(ResourceDimension.RETRIEVAL_ROUNDS):
            return []
        self.reserve(ResourceDimension.RETRIEVAL_ROUNDS)
        remaining_candidates = int(
            self.meters[ResourceDimension.RETRIEVAL_CANDIDATES].remaining()
        )
        cap = (
            min(limit or remaining_candidates, remaining_candidates)
            if remaining_candidates > 0
            else 0
        )
        if cap <= 0:
            self.commit(ResourceDimension.RETRIEVAL_ROUNDS)
            return []
        result = self.runtime.search_corpus(query, SearchOptions(limit=cap))
        chunk_ids = [c.chunk_id for c in result.chunks]
        self.commit(ResourceDimension.RETRIEVAL_ROUNDS)
        for _ in chunk_ids:
            if not self.reserve(ResourceDimension.RETRIEVAL_CANDIDATES):
                break
            self.commit(ResourceDimension.RETRIEVAL_CANDIDATES)
        return chunk_ids

    def verify(self, claim_text: str) -> str | None:
        """Create + verify a claim (admission-gated)."""
        if not self.can(ResourceDimension.VERIFICATION_ROUNDS):
            return None
        self.reserve(ResourceDimension.VERIFICATION_ROUNDS)
        claim = self.runtime.create_claim(self.project_id, claim_text)
        self.state.claims.append(claim.claim_id)
        report = self.runtime.verify_claim(self.project_id, claim.claim_id)
        self.commit(ResourceDimension.VERIFICATION_ROUNDS)
        report_id: str = report.report_id
        self.state.verification_refs.append(report_id)
        return report_id

    def contradictions(self) -> list[str]:
        """Detect contradictions (admission-gated)."""
        if not self.can(ResourceDimension.VERIFICATION_ROUNDS):
            return []
        self.reserve(ResourceDimension.VERIFICATION_ROUNDS)
        found = self.runtime.get_contradictions(self.project_id)
        self.commit(ResourceDimension.VERIFICATION_ROUNDS)
        ids = [c.contradiction_id for c in found]
        self.state.contradictions.extend(ids)
        return ids

    def compute(self, dataset_ref: Any) -> str | None:
        """Run a bounded computation (admission-gated)."""
        if not self.can(ResourceDimension.COMPUTATION_ROUNDS):
            return None
        self.reserve(ResourceDimension.COMPUTATION_ROUNDS)
        from qwen_research.computation.models import ComputationOperation

        result = self.runtime.run_analysis(
            self.project_id, (dataset_ref,), ComputationOperation.SUMMARIZE
        )
        self.commit(ResourceDimension.COMPUTATION_ROUNDS)
        computation_id: str = result.computation_id
        self.state.computation_refs.append(computation_id)
        return computation_id

    def critique(self, draft: str, *, claims: tuple[str, ...] = ()) -> CritiqueResult:
        """Model-backed critique over the actual draft (admission-gated)."""
        if not self.can(ResourceDimension.CRITIQUE_ROUNDS):
            return CritiqueResult(
                recommended_action=CritiqueAction.NO_ACTION,
                recommendation_reason="critique budget exhausted",
            )
        self.reserve(ResourceDimension.CRITIQUE_ROUNDS)
        result = self.invoke(
            (
                Message(role=MessageRole.SYSTEM, content=_CRITIQUE_SYSTEM),
                Message(
                    role=MessageRole.USER,
                    content=f"Draft: {draft}\nClaims: {', '.join(claims) or '(none)'}",
                ),
            )
        )
        self.commit(ResourceDimension.CRITIQUE_ROUNDS)
        parsed = _parse_critique(result.content)
        self.state.critique_results.append(parsed)
        return parsed

    def rewrite(self, draft: str, critique: CritiqueResult) -> str:
        """Generate a revised draft resolving the critic's issue."""
        issue = critique.issues[0].description if critique.issues else "the critic's issue"
        result = self.invoke(
            (
                Message(role=MessageRole.SYSTEM, content=_REWRITE_SYSTEM),
                Message(
                    role=MessageRole.USER,
                    content=f"Draft: {draft}\nCritic issue: {issue}\nRevise the draft.",
                ),
            )
        )
        return result.content

    def synthesize(self, synth_input: ResearchSynthesisInput) -> InferenceResult:
        """Evidence-aware synthesis (admission-gated)."""
        if not self.can(ResourceDimension.SYNTHESIS_PASSES):
            raise _BudgetExhaustedError("synthesis budget exhausted")
        self.reserve(ResourceDimension.SYNTHESIS_PASSES)
        user = (
            f"Objective: {self.state.task_description}\n"
            f"Evidence refs: {', '.join(synth_input.evidence_refs) or '(none)'}\n"
            f"Verified claims: {', '.join(self.state.claims) or '(none)'}\n"
            f"Contradictions: {', '.join(self.state.contradictions) or '(none)'}\n"
            f"Unresolved: {', '.join(synth_input.unresolved_questions) or '(none)'}\n"
            "Produce a grounded synthesis."
        )
        result = self.invoke(
            (
                Message(role=MessageRole.SYSTEM, content=_SYNTHESIS_SYSTEM),
                Message(role=MessageRole.USER, content=user),
            )
        )
        self.commit(ResourceDimension.SYNTHESIS_PASSES)
        return result

    def run_tool_loop(self, request: InferenceRequest) -> Any:
        """Run the Phase-9 tool loop with the remaining tool budget as a hard cap.

        The tool loop's ``max_tool_calls`` is bounded by the remaining
        high-effort tool-call budget, so the lower layer can never execute more
        tool calls than remain.
        """
        remaining = int(self.meters[ResourceDimension.TOOL_CALLS].remaining())
        if remaining <= 0:
            raise _BudgetExhaustedError("tool budget exhausted")
        from qwen_research.research.tool_loop import ToolLoopConfig

        config = ToolLoopConfig(max_tool_calls=remaining)
        result = self.runtime.run_tool_loop(request, project_id=self.project_id, config=config)
        self.commit(ResourceDimension.TOOL_CALLS, float(result.accounting.tool_calls))
        self.commit(ResourceDimension.INFERENCE_CALLS, float(result.accounting.inference_calls))
        return result

    # -- critique action dispatcher (real work, not counter decrements) ----

    def apply_critique_action(self, action: CritiqueAction, draft: str) -> tuple[str, bool]:
        """Execute a critique action with real work. Returns (draft, changed)."""
        if action is CritiqueAction.RETRIEVE_MORE:
            if self.can(ResourceDimension.RETRIEVAL_ROUNDS):
                extra = self.retrieve(self.state.task_description)
                self.state.evidence_refs.extend(extra)
                return draft, bool(extra)
            return draft, False
        if action is CritiqueAction.VERIFY_MORE:
            if self.can(ResourceDimension.VERIFICATION_ROUNDS):
                return draft, self.verify(self.state.task_description) is not None
            return draft, False
        if action is CritiqueAction.COMPUTE_MORE:
            if self.can(ResourceDimension.COMPUTATION_ROUNDS):
                # No dataset configured → cannot compute; report no change.
                return draft, False
            return draft, False
        if action is CritiqueAction.REWRITE or action is CritiqueAction.REJECT_DRAFT:
            if self.can(ResourceDimension.SYNTHESIS_PASSES):
                revised = self.rewrite(draft, self.state.critique_results[-1])
                return revised, revised != draft
            return draft, False
        return draft, False

    def reallocate_after_signal(self, signal: BudgetSignal) -> None:
        self.scheduler.apply_signal(signal)

    def checkpoint(self) -> None:
        if self.store is not None:
            self.store.save_state(self.state)


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
    violations: tuple[str, ...] = ()
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
    """Run a bounded high-effort research execution against a real runtime."""
    run_id = run_id or new_id("run")

    state = store.load_state(run_id) if store is not None else None
    if state is None:
        state = HighEffortRunState(
            run_id=run_id,
            profile=profile_name,
            task_description=task_description,
            budget=get_test_time_policy(profile_name).budget(),
        )

    engine = HighEffortEngine(runtime, profile_name, state, project_id=project_id, store=store)

    try:
        _execute(engine, trajectory_strategies, dataset_ref=dataset_ref, tool_request=tool_request)
    except _BudgetExhaustedError as exc:
        state.status = RunStatus.BUDGET_EXHAUSTED.value
        engine.checkpoint()
        return _finalize(engine, state, error=f"{exc}")
    except Exception as exc:  # noqa: BLE001 — normalize run failure
        state.status = RunStatus.FAILED.value
        engine.checkpoint()
        return _finalize(engine, state, error=f"{type(exc).__name__}: {exc}")

    engine.checkpoint()
    return _finalize(engine, state)


def _execute(
    engine: HighEffortEngine,
    trajectory_strategies: tuple[TrajectoryStrategy, ...],
    *,
    dataset_ref: Any,
    tool_request: InferenceRequest | None,
) -> None:
    state = engine.state

    # 1. Trajectories (admit + retrieve); resume skips already-completed ones.
    for strategy in trajectory_strategies:
        existing = next((t for t in state.trajectories if t.strategy is strategy), None)
        if existing is not None and existing.status == TrajectoryStatus.COMPLETED.value:
            continue
        if existing is None:
            if not engine.should_continue() or not engine.reserve(ResourceDimension.TRAJECTORIES):
                break
            engine.commit(ResourceDimension.TRAJECTORIES)
            existing = ResearchTrajectory.create(strategy, state.task_description)
            existing = dataclasses.replace(existing, status=TrajectoryStatus.RUNNING.value)
            state.trajectories.append(existing)
            engine.checkpoint()

        # Execute the trajectory's retrieval against the global budget.
        qset = trajectory_query_set(strategy, state.task_description)
        evidence: list[str] = list(existing.evidence_refs)
        for query in qset.all_queries():
            if not engine.should_continue():
                break
            evidence.extend(engine.retrieve(query))
        # Record evidence at run scope too (completion depends on it).
        for ref in evidence:
            if ref not in state.evidence_refs:
                state.evidence_refs.append(ref)
        # Determine the trajectory's final status honestly.
        status = TrajectoryStatus.COMPLETED
        if engine.deadline_exceeded():
            status = TrajectoryStatus.TIME_LIMIT
        elif engine.budget.all_exhausted():
            status = TrajectoryStatus.BUDGET_EXHAUSTED
        elif not evidence:
            status = TrajectoryStatus.BLOCKED
        state.trajectories = [
            dataclasses.replace(
                t,
                evidence_refs=tuple(evidence),
                status=status.value,
            ) if t.trajectory_id == existing.trajectory_id else t
            for t in state.trajectories
        ]
        engine.checkpoint()

    # 2. Verification.
    if (
        "verification" not in state.completed_stages
        and engine.should_continue()
        and engine.can(ResourceDimension.VERIFICATION_ROUNDS)
    ):
        try:
            engine.verify(state.task_description or "research objective")
            state.completed_stages.append("verification")
            engine.checkpoint()
        except UnsupportedOperationError:
            pass

    # 3. Contradiction search (adaptive escalation).
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
                        ResourceDimension.VERIFICATION_ROUNDS,
                        "strong",
                        "contradiction found",
                    )
                )
            engine.checkpoint()
        except UnsupportedOperationError:
            pass

    # 4. Computation.
    if (
        dataset_ref is not None
        and "computation" not in state.completed_stages
        and engine.should_continue()
        and engine.can(ResourceDimension.COMPUTATION_ROUNDS)
    ):
        try:
            engine.compute(dataset_ref)
            state.completed_stages.append("computation")
            engine.checkpoint()
        except UnsupportedOperationError:
            pass

    # 5. Tool loop.
    if (
        tool_request is not None
        and "tool_loop" not in state.completed_stages
        and engine.should_continue()
    ):
        engine.run_tool_loop(tool_request)
        state.completed_stages.append("tool_loop")
        engine.checkpoint()

    # 6. Draft → critique → action → revision → final critique.
    if (
        state.draft_status == DraftStatus.DRAFT.value
        and engine.can(ResourceDimension.SYNTHESIS_PASSES)
    ):
        draft_result = engine.synthesize(_synthesis_input(state))
        state.draft = draft_result.content
        state.draft_status = DraftStatus.CRITIQUED.value
        engine.checkpoint()

    _critique_loop(engine)

    # 7. Final verification + synthesis.
    if state.final_verified or engine.can(ResourceDimension.VERIFICATION_ROUNDS):
        if not state.final_verified:
            engine.verify(state.task_description or "research objective")
            state.final_verified = True
        state.draft_status = DraftStatus.FINAL_VERIFIED.value
        engine.checkpoint()

    if "synthesis" not in state.completed_stages and engine.can(ResourceDimension.SYNTHESIS_PASSES):
        synth_input = _synthesis_input(state)
        result = engine.synthesize(synth_input)
        state.completed_stages.append("synthesis")
        state.final_synthesis = result.content
        engine.checkpoint()


def _critique_loop(engine: HighEffortEngine) -> None:
    state = engine.state
    rounds = 0
    draft = state.draft
    while rounds < state.budget.allocated.get(ResourceDimension.CRITIQUE_ROUNDS, 0):
        if not engine.can(ResourceDimension.CRITIQUE_ROUNDS):
            break
        critique = engine.critique(draft, claims=tuple(state.claims))
        state.draft_status = DraftStatus.CRITIQUED.value
        if critique.recommended_action is CritiqueAction.NO_ACTION:
            break
        state.draft_status = DraftStatus.REVISION_REQUIRED.value
        revised, changed = engine.apply_critique_action(critique.recommended_action, draft)
        if changed:
            draft = revised
            state.draft = draft
            state.draft_status = DraftStatus.REVISED.value
        elif critique.recommended_action in (CritiqueAction.REWRITE, CritiqueAction.REJECT_DRAFT):
            state.draft_status = DraftStatus.REJECTED.value
            break
        engine.checkpoint()
        rounds += 1
    state.draft = draft
    state.draft_status = DraftStatus.FINAL_CANDIDATE.value
    engine.checkpoint()


def _synthesis_input(state: HighEffortRunState) -> ResearchSynthesisInput:
    return ResearchSynthesisInput(
        claims=tuple(state.claims),
        evidence_refs=tuple(state.evidence_refs),
        verification_refs=tuple(state.verification_refs),
        contradictions=tuple(state.contradictions),
        computations=tuple(state.computation_refs),
        trajectory_findings=tuple(t.trajectory_id for t in state.trajectories),
        critique_findings=tuple(
            i.description for c in state.critique_results for i in c.issues
        ),
        unresolved_questions=(),
    )


def _completion_met(state: HighEffortRunState) -> bool:
    """Completion requires evidence, verification, a critiqued draft, and no
    unresolved contradiction (conservative: any recorded contradiction blocks)."""
    return bool(
        state.evidence_refs
        and state.verification_refs
        and state.draft
        and state.draft_status
        in (DraftStatus.FINAL_CANDIDATE.value, DraftStatus.FINAL_VERIFIED.value)
        and not state.contradictions
    )


def _finalize(
    engine: HighEffortEngine, state: HighEffortRunState, *, error: str | None = None
) -> HighEffortResult:
    if error is not None:
        status = RunStatus.BUDGET_EXHAUSTED
    elif engine.deadline_exceeded():
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
        violations=tuple(state.violations),
        error=error,
    )


def _parse_critique(content: str) -> CritiqueResult:
    """Deterministic, model-output-driven critique parsing."""
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
    elif "recompute" in text or "numerical" in text:
        issues.append(CritiqueIssue(severity="major", description="numerical error"))
        action = CritiqueAction.COMPUTE_MORE
    else:
        issues.append(CritiqueIssue(severity="warning", description=content.strip()))
        action = CritiqueAction.REWRITE
    return CritiqueResult(issues=tuple(issues), recommended_action=action)
