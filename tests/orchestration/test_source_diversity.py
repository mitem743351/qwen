"""Phase 7.2 source-diversity consistency tests.

Verifies workflow completion reuses the Phase-5 SourceIndependence subsystem
(rather than a raw document count) for "independent sources" / "source
diversity" requirements, and that the two metrics — document count and
independent-source count — stay distinct.
"""

from __future__ import annotations

from pathlib import Path

from qwen_research.orchestration.diversity import (
    SourceDiversity,
    evaluate_source_diversity,
    source_diversity_from_outputs,
    source_identities_from,
)
from qwen_research.orchestration.engine import WorkflowEngine
from qwen_research.orchestration.models import (
    CompletionCriteria,
    PlanRequirements,
    ResearchPlan,
    ResearchStage,
    ResearchTask,
    RunStatus,
    StageResult,
    StageType,
    TaskComplexity,
    TaskType,
    WorkflowRun,
)
from qwen_research.orchestration.stages import StageExecutionContext
from qwen_research.orchestration.store import OrchestrationStore
from qwen_research.sources.independence import count_independent_sources


def _identities(*entries: dict[str, str | None]) -> list:
    return list(entries)


def _ident(
    id_: str, source: str | None, publisher: str | None, root: str = "r"
) -> dict[str, str | None]:
    return {"document_id": id_, "source_id": source, "publisher": publisher, "root_id": root}


# -- unit: evaluate_source_diversity ---------------------------------------

def test_two_independent_sources() -> None:
    div = evaluate_source_diversity(
        source_identities_from(_identities(_ident("d1", "s1", "A"), _ident("d2", "s2", "B")))
    )
    assert div.document_count == 2
    assert div.independent_source_count == 2


def test_two_same_publisher_documents_are_not_independent() -> None:
    div = evaluate_source_diversity(
        source_identities_from(_identities(_ident("d1", "s1", "X"), _ident("d2", "s2", "X")))
    )
    assert div.document_count == 2
    assert div.independent_source_count == 1


def test_same_document_chunks_are_one_source() -> None:
    div = evaluate_source_diversity(
        source_identities_from(
            _identities(
                _ident("d1", "s1", None),
                _ident("d1", "s1", None),
                _ident("d1", "s1", None),
            )
        )
    )
    assert div.document_count == 1
    assert div.independent_source_count == 1


def test_same_source_identity_multiple_documents_is_dependent() -> None:
    # Two distinct documents sharing a source_id must collapse (Phase-5 rule).
    div = evaluate_source_diversity(
        source_identities_from(_identities(_ident("d1", "sX", None), _ident("d2", "sX", None)))
    )
    assert div.document_count == 2
    assert div.independent_source_count == 1


def test_unknown_source_identity_is_not_fabricated_as_independent() -> None:
    # source_id unknown (None) + same root → UNKNOWN per Phase-5, never invented.
    div = evaluate_source_diversity(
        source_identities_from(_identities(_ident("d1", None, None), _ident("d2", None, None)))
    )
    # The authoritative count is whatever count_independent_sources returns;
    # it must never be a naive document count (2) here.
    authoritative = count_independent_sources(
        source_identities_from(_identities(_ident("d1", None, None), _ident("d2", None, None)))
    )
    assert div.independent_source_count == authoritative


def test_mixed_source_groups() -> None:
    # d1/d2 same publisher (1 group); d3 independent; d4 = d3 (same doc).
    div = evaluate_source_diversity(
        source_identities_from(
            _identities(
                _ident("d1", "s1", "acme"),
                _ident("d2", "s2", "acme"),
                _ident("d3", "s3", "beta"),
                _ident("d3", "s3", "beta"),
            )
        )
    )
    assert div.document_count == 3
    assert div.independent_source_count == 2


def test_diversity_matches_phase5_count() -> None:
    ids = source_identities_from(
        _identities(
            _ident("d1", "s1", "acme"),
            _ident("d2", "s2", "acme"),
            _ident("d3", "s3", "beta"),
        )
    )
    div = evaluate_source_diversity(ids)
    assert div.independent_source_count == count_independent_sources(ids)
    assert isinstance(div, SourceDiversity)


# -- completion integration -------------------------------------------------

class _RetrieveEvidenceExecutor:
    """A retrieve stage that emits fixed candidate evidence identities."""

    def __init__(self, identities: list[dict[str, str | None]]) -> None:
        self._identities = identities

    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.RETRIEVE

    def execute(self, context: StageExecutionContext) -> StageResult:
        return StageResult.completed(
            {
                "evidence": tuple(f"chunk_{i}" for i in range(len(self._identities))),
                "evidence_sources": tuple(
                    sorted(
                        {i["document_id"] for i in self._identities if i["document_id"]}
                    )
                ),
                "evidence_identities": tuple(self._identities),
            },
            references=tuple(f"chunk_{i}" for i in range(len(self._identities))),
            metrics={"retrieval_calls": 1},
        )


def _engine_with_retrieve(
    tmp_path: Path,
    identities: list[dict[str, str | None]],
    min_source_diversity: int,
) -> tuple[WorkflowEngine, ResearchTask, ResearchPlan]:
    store = OrchestrationStore(tmp_path / "orch.db")
    store.initialize()
    task = ResearchTask.create("p", "task", TaskType.CUSTOM, TaskComplexity.SIMPLE, "FAST")
    store.save_task(task)
    stages = (ResearchStage(stage_id="retrieve", type=StageType.RETRIEVE, name="retrieve"),)
    plan = ResearchPlan.create(
        task.task_id,
        "task",
        stages,
        requirements=PlanRequirements(needs_retrieval=True),
        completion_criteria=CompletionCriteria(
            min_evidence_count=1, min_source_diversity=min_source_diversity
        ),
    )
    store.save_plan(plan, project_id="p")
    engine = WorkflowEngine(
        store, executors={StageType.RETRIEVE: _RetrieveEvidenceExecutor(identities)}
    )
    return engine, task, plan


def _run(engine: WorkflowEngine, task: ResearchTask, plan: ResearchPlan) -> WorkflowRun:
    run = engine.create_run(task, plan)
    return engine.execute_until_blocked(run.run_id)


def test_completion_satisfied_with_two_independent_sources(tmp_path: Path) -> None:
    engine, task, plan = _engine_with_retrieve(
        tmp_path,
        [_ident("d1", "s1", "A"), _ident("d2", "s2", "B")],
        min_source_diversity=2,
    )
    run = _run(engine, task, plan)
    assert run.status is RunStatus.READY_FOR_SYNTHESIS


def test_completion_not_satisfied_by_same_publisher(tmp_path: Path) -> None:
    # Two documents, same publisher → independent_source_count = 1 < 2 → PARTIAL.
    engine, task, plan = _engine_with_retrieve(
        tmp_path,
        [_ident("d1", "s1", "X"), _ident("d2", "s2", "X")],
        min_source_diversity=2,
    )
    run = _run(engine, task, plan)
    assert run.status is RunStatus.PARTIAL
    # The diagnostic must be explicit, not a misleading "source diversity: 2".
    joined = " | ".join(run.completion_notes)
    assert "required independent sources: 2" in joined
    assert "found independent sources: 1" in joined
    assert "documents represented: 2" in joined


def test_completion_same_document_chunks_not_satisfied(tmp_path: Path) -> None:
    engine, task, plan = _engine_with_retrieve(
        tmp_path,
        [_ident("d1", "s1", None), _ident("d1", "s1", None), _ident("d1", "s1", None)],
        min_source_diversity=2,
    )
    run = _run(engine, task, plan)
    assert run.status is RunStatus.PARTIAL
    joined = " | ".join(run.completion_notes)
    assert "found independent sources: 1" in joined
    assert "documents represented: 1" in joined


def test_outputs_diversity_helper() -> None:
    outputs: dict[str, object] = {
        "evidence_identities": [_ident("d1", "s1", "X"), _ident("d2", "s2", "X")]
    }
    div = source_diversity_from_outputs(outputs)
    assert div.document_count == 2
    assert div.independent_source_count == 1
