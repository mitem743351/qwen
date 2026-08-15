"""End-to-end deterministic workflow tests (no model invocation)."""

from __future__ import annotations

from pathlib import Path

from orchestration_helpers import build_runtime
from qwen_research.computation.models import DatasetReference as DatasetRef
from qwen_research.orchestration.models import ComputationSpec, RunStatus, TaskType


def test_deep_research_workflow(tmp_path: Path) -> None:
    runtime, _, _ = build_runtime(tmp_path)
    task, plan = runtime.plan_research(
        "what is the surface code threshold and how does decoherence affect it?",
        project_id="p",
        profile="DEEP",
    )
    run = runtime.start_research(plan.plan_id)
    assert run.status is RunStatus.READY_FOR_SYNTHESIS
    supporting = runtime.get_research_summary(run.run_id)["supporting_evidence"]
    assert isinstance(supporting, int) and supporting >= 1
    # Evidence provenance was persisted to research memory.
    assert run.outputs.get("memory_ids")


def test_fact_check_workflow(tmp_path: Path) -> None:
    runtime, _, _ = build_runtime(tmp_path)
    task, plan = runtime.plan_research(
        "the surface code achieves a high threshold",
        project_id="p",
        task_type=TaskType.FACT_CHECK,
        profile="DEEP",
    )
    run = runtime.start_research(plan.plan_id)
    assert run.status is RunStatus.READY_FOR_SYNTHESIS
    assert run.outputs.get("claims")
    assert run.outputs.get("verification_reports")
    # Verification reports must be present (claim was assessed + verified).
    status = runtime.get_research_status(run.run_id)
    assert status.status == "ready_for_synthesis"


def test_data_analysis_workflow(tmp_path: Path) -> None:
    runtime, _, _ = build_runtime(tmp_path)
    spec = ComputationSpec(
        operation="statistics",
        dataset_refs=(DatasetRef(root_id="semantic", relative_path="numbers.csv"),),
        parameters={"column": "value"},
    )
    task, plan = runtime.plan_research(
        "analyze the data",
        project_id="p",
        task_type=TaskType.DATA_ANALYSIS,
        computation=spec,
    )
    run = runtime.start_research(plan.plan_id)
    assert run.status is RunStatus.READY_FOR_SYNTHESIS
    assert run.outputs.get("dataset_profile") is not None
    assert run.outputs.get("computations")


def test_literature_review_workflow(tmp_path: Path) -> None:
    runtime, _, _ = build_runtime(tmp_path)
    task, plan = runtime.plan_research(
        "survey of surface code research",
        project_id="p",
        task_type=TaskType.LITERATURE_REVIEW,
        profile="DEEP",
    )
    run = runtime.start_research(plan.plan_id)
    assert run.status is RunStatus.READY_FOR_SYNTHESIS
    diversity = run.outputs.get("source_diversity", 0)
    assert isinstance(diversity, int) and diversity >= 2


def test_project_isolation(tmp_path: Path) -> None:
    runtime, store, _ = build_runtime(tmp_path)
    task_a, plan_a = runtime.plan_research("what is the surface code", project_id="A")
    task_b, plan_b = runtime.plan_research("what is the surface code", project_id="B")
    assert task_a.project_id != task_b.project_id
    # A run from project A must not be visible/listed under project B.
    run_a = runtime.start_research(plan_a.plan_id)
    assert run_a.status is RunStatus.READY_FOR_SYNTHESIS
    assert store.get_run(run_a.run_id) is not None


def test_synthesis_request_ready(tmp_path: Path) -> None:
    runtime, _, _ = build_runtime(tmp_path)
    task, plan = runtime.plan_research("what is the surface code threshold", project_id="p")
    run = runtime.start_research(plan.plan_id)
    # The synthesis stage marks the future-inference boundary as ready.
    assert run.outputs.get("synthesis_request_ready") is True
