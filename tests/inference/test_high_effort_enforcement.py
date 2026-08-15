"""Phase 10.2 enforcement tests: hard budgets, deadlines, checkpoint, critique."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    Message,
    MessageRole,
)
from qwen_research.domain.test_time import (
    HighEffortRunState,
    ResourceDimension,
    TrajectoryStatus,
    TrajectoryStrategy,
    get_test_time_policy,
)
from qwen_research.research.budget_store import SqliteRunStateStore
from qwen_research.research.high_effort import HighEffortEngine
from qwen_research.research.scheduler import BudgetSignal

# -- token enforcement ----------------------------------------------------

def test_token_budget_bounds_max_output_tokens() -> None:
    seen: list[InferencePolicy] = []

    class _Runtime:
        def invoke_inference(self, request: InferenceRequest) -> InferenceResult:
            seen.append(request.inference_policy)
            return InferenceResult(status="ok", model="qwen3.8-max-preview", content="x")

    state = HighEffortRunState(
        run_id="r", profile="NORMAL", task_description="t",
        budget=get_test_time_policy("NORMAL").budget(),
    )
    # Force a small remaining token budget.
    state.budget.allocated[ResourceDimension.TOKENS] = 1000.0
    engine = HighEffortEngine(_Runtime(), "NORMAL", state)
    engine.invoke((Message(role=MessageRole.SYSTEM, content="x"),))
    # The request's max_output_tokens must be bounded by the remaining token budget.
    assert seen[0].max_output_tokens == 1000


def test_token_overrun_is_flagged_not_clamped() -> None:
    class _Runtime:
        def invoke_inference(self, request: InferenceRequest) -> InferenceResult:
            # Provider reports usage larger than the budget.
            return InferenceResult(
                status="ok", model="m", content="x",
                usage={"total_tokens": 5000},
            )

    state = HighEffortRunState(
        run_id="r", profile="NORMAL", task_description="t",
        budget=get_test_time_policy("NORMAL").budget(),
    )
    state.budget.allocated[ResourceDimension.TOKENS] = 1000.0
    engine = HighEffortEngine(_Runtime(), "NORMAL", state)
    engine.invoke((Message(role=MessageRole.SYSTEM, content="x"),))
    # Overrun is recorded as a violation, never silently hidden.
    assert state.violations


# -- retrieval candidate budget ------------------------------------------

def test_retrieval_candidate_limit_bounded_by_remaining() -> None:
    seen_limits: list[int] = []

    class _Runtime:
        def search_corpus(self, query: str, options: Any = None) -> Any:
            seen_limits.append(options.limit)
            return SimpleNamespace(chunks=[SimpleNamespace(chunk_id="c")])

    state = HighEffortRunState(
        run_id="r", profile="NORMAL", task_description="t",
        budget=get_test_time_policy("NORMAL").budget(),
    )
    # Only 3 retrieval candidates remain.
    state.budget.allocated[ResourceDimension.RETRIEVAL_CANDIDATES] = 3.0
    engine = HighEffortEngine(_Runtime(), "NORMAL", state)
    engine.retrieve("q")
    assert seen_limits == [3]


# -- deadline persistence ------------------------------------------------

def test_deadline_persisted_and_restored(tmp_path: Path) -> None:
    store = SqliteRunStateStore(tmp_path / "runs.db")
    store.initialize()
    state = HighEffortRunState(
        run_id="r", profile="XHIGH", task_description="t",
        budget=get_test_time_policy("XHIGH").budget(),
    )
    engine = HighEffortEngine(SimpleNamespace(), "XHIGH", state, store=store)
    engine.checkpoint()

    loaded = store.load_state("r")
    assert loaded is not None
    assert loaded.deadline_at is not None
    assert loaded.deadline_at == state.deadline_at


def test_expired_deadline_does_not_resume() -> None:
    state = HighEffortRunState(
        run_id="r", profile="XHIGH", task_description="t",
        budget=get_test_time_policy("XHIGH").budget(),
        deadline_at=0.0,  # long expired
    )
    engine = HighEffortEngine(SimpleNamespace(), "XHIGH", state)
    assert engine.deadline_exceeded()
    assert not engine.should_continue()


# -- trajectory status (no false COMPLETED) -------------------------------

def test_trajectory_not_completed_on_budget_exhaustion() -> None:
    calls: list[str] = []

    class _Runtime:
        def search_corpus(self, query: str, options: Any = None) -> Any:
            calls.append(query)
            return SimpleNamespace(chunks=[])

    state = HighEffortRunState(
        run_id="r", profile="FAST", task_description="t",
        budget=get_test_time_policy("FAST").budget(),
    )
    # Exhaust the whole budget so trajectories cannot complete.
    for dim in list(state.budget.allocated):
        state.budget.commit(dim, state.budget.allocated[dim])
    engine = HighEffortEngine(_Runtime(), "FAST", state)

    from qwen_research.research.high_effort import _execute

    _execute(engine, (TrajectoryStrategy.DIRECT,), dataset_ref=None, tool_request=None)
    # No trajectory is admitted at all (budget exhausted before admission).
    assert all(t.status != TrajectoryStatus.COMPLETED.value for t in state.trajectories)


# -- budget conservation --------------------------------------------------

def test_reallocation_conserves_total_budget() -> None:
    state = HighEffortRunState(
        run_id="r", profile="XHIGH", task_description="t",
        budget=get_test_time_policy("XHIGH").budget(),
    )
    engine = HighEffortEngine(SimpleNamespace(), "XHIGH", state)
    before = sum(state.budget.allocated.values())
    engine.reallocate_after_signal(
        BudgetSignal(ResourceDimension.RETRIEVAL_ROUNDS, "weak", "weak evidence")
    )
    after = sum(state.budget.allocated.values())
    assert after == before


# -- critique action dispatches real work ---------------------------------

def test_critique_retrieve_more_dispatches_retrieval() -> None:
    calls: list[str] = []

    class _Runtime:
        def search_corpus(self, query: str, options: Any = None) -> Any:
            calls.append(query)
            return SimpleNamespace(chunks=[SimpleNamespace(chunk_id="e1")])

    state = HighEffortRunState(
        run_id="r", profile="XHIGH", task_description="task",
        budget=get_test_time_policy("XHIGH").budget(),
    )
    engine = HighEffortEngine(_Runtime(), "XHIGH", state)
    from qwen_research.domain.test_time import CritiqueAction, CritiqueResult

    engine.state.critique_results.append(
        CritiqueResult(recommended_action=CritiqueAction.RETRIEVE_MORE)
    )
    engine.apply_critique_action(CritiqueAction.RETRIEVE_MORE, "draft")
    assert calls == ["task"]  # a real retrieval happened
    assert state.evidence_refs == ["e1"]


# -- budget bypass --------------------------------------------------------

def test_exhausted_dimension_blocks_child_operation() -> None:
    calls: list[str] = []

    class _Runtime:
        def search_corpus(self, query: str, options: Any = None) -> Any:
            calls.append(query)
            return SimpleNamespace(chunks=[SimpleNamespace(chunk_id="c")])

    state = HighEffortRunState(
        run_id="r", profile="FAST", task_description="t",
        budget=get_test_time_policy("FAST").budget(),
    )
    state.budget.allocated[ResourceDimension.RETRIEVAL_ROUNDS] = 0.0
    engine = HighEffortEngine(_Runtime(), "FAST", state)
    assert engine.retrieve("q") == []
    assert calls == []  # the child runtime was never invoked


# -- inference-call budget ------------------------------------------------

def test_inference_budget_blocks_extra_calls() -> None:
    calls: list[str] = []

    class _Runtime:
        def invoke_inference(self, request: InferenceRequest) -> InferenceResult:
            calls.append(request.inference_policy.model_requirement or "")
            return InferenceResult(status="ok", model="m", content="x")

    state = HighEffortRunState(
        run_id="r", profile="FAST", task_description="t",
        budget=get_test_time_policy("FAST").budget(),
    )
    state.budget.allocated[ResourceDimension.INFERENCE_CALLS] = 1.0
    engine = HighEffortEngine(_Runtime(), "FAST", state)
    engine.invoke((Message(role=MessageRole.SYSTEM, content="x"),))

    from qwen_research.research.high_effort import _BudgetExhaustedError

    with pytest.raises(_BudgetExhaustedError):
        engine.invoke((Message(role=MessageRole.SYSTEM, content="x"),))
    assert len(calls) == 1
