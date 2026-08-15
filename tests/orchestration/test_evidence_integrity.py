"""Regression tests for neutral evidence semantics and honest completion.

These prove the Phase 7 workflow never manufactures evidence support from
retrieval, reuses Phase-5 SourceIndependence for corroboration, distinguishes
workflow-complete from answer-complete, and surfaces missing capabilities as
explicit degradation.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from orchestration_helpers import build_stack
from qwen_research.orchestration.capabilities import CapabilityRegistry
from qwen_research.orchestration.models import (
    ResearchCapability,
    ResearchPlan,
    ResearchTask,
    RunStatus,
    StageType,
    TaskComplexity,
    TaskType,
    WorkflowGuardrails,
    WorkflowRun,
    as_str_tuple,
)
from qwen_research.orchestration.planning import ResearchPlanner
from qwen_research.orchestration.service import OrchestrationService
from qwen_research.orchestration.stages import (
    CorroborateExecutor,
    StageExecutionContext,
    StageRuntime,
)
from qwen_research.verification.models import VerificationStatus


def test_retrieval_cannot_manufacture_support(tmp_path: Path) -> None:
    """A FACT_CHECK run must not create any claim→evidence SUPPORTS links."""
    s = build_stack(tmp_path)
    runtime = s["runtime"]
    vstore = s["verification_store"]

    task, plan = runtime.plan_research(
        "the surface code achieves a high threshold",
        project_id="p",
        task_type=TaskType.FACT_CHECK,
        profile="DEEP",
    )
    run = runtime.start_research(plan.plan_id)

    claims = as_str_tuple(run.outputs.get("claims"))
    assert claims, "a claim should have been created"

    # No claim→evidence links were manufactured by retrieval/assessment.
    for claim_id in claims:
        assert vstore.get_links(claim_id) == [], (
            "retrieval/assessment must never create claim-evidence links"
        )

    # The claim verified as INSUFFICIENT_EVIDENCE (no support was fabricated).
    assert "insufficient_evidence" in as_str_tuple(run.outputs.get("verification_statuses"))
    # The run is workflow-complete but not answer-complete.
    assert run.status is RunStatus.READY_FOR_SYNTHESIS


def test_assess_records_neutral_candidate_evidence(tmp_path: Path) -> None:
    """Assessment marks candidate evidence neutrally, never as SUPPORTS."""
    s = build_stack(tmp_path)
    runtime = s["runtime"]
    vstore = s["verification_store"]

    task, plan = runtime.plan_research(
        "the surface code achieves a high threshold",
        project_id="p",
        task_type=TaskType.FACT_CHECK,
        profile="DEEP",
    )
    run = runtime.start_research(plan.plan_id)

    # Neutral candidate evidence is recorded; no links are created.
    assert "candidate_evidence" in run.outputs
    assert "assessed_links" not in run.outputs
    assert "links_created" not in run.accounting
    for claim_id in as_str_tuple(run.outputs.get("claims")):
        assert vstore.get_links(claim_id) == []


def _corroborate_context(identities: tuple[dict, ...]) -> StageExecutionContext:
    task = ResearchTask.create(
        "p", "t", TaskType.LITERATURE_REVIEW, TaskComplexity.SIMPLE, "FAST"
    )
    plan = ResearchPlan.create(task.task_id, "t", ())
    run = WorkflowRun.create(task.task_id, plan, "wf")
    return StageExecutionContext(
        task=task,
        plan=plan,
        run=run,
        project_id="p",
        runtime=cast(StageRuntime, object()),  # corroborate never calls runtime
        outputs={"evidence_identities": identities},
        guardrails=WorkflowGuardrails(),
    )


def test_corroboration_uses_source_independence() -> None:
    executor = CorroborateExecutor()
    assert executor.supports(StageType.CORROBORATE)

    # Two chunks from the SAME document collapse to one independent source.
    same_doc = executor.execute(
        _corroborate_context(
            (
                {"document_id": "d1", "source_id": "s1", "root_id": "r", "publisher": None},
                {"document_id": "d1", "source_id": "s1", "root_id": "r", "publisher": None},
            )
        )
    )
    assert same_doc.outputs["independent_source_count"] == 1

    # Two chunks from DIFFERENT documents/sources are independent.
    diff_doc = executor.execute(
        _corroborate_context(
            (
                {"document_id": "d1", "source_id": "s1", "root_id": "r", "publisher": None},
                {"document_id": "d2", "source_id": "s2", "root_id": "r", "publisher": None},
            )
        )
    )
    assert diff_doc.outputs["independent_source_count"] == 2

    # Same publisher across different documents is NOT independent.
    same_pub = executor.execute(
        _corroborate_context(
            (
                {"document_id": "d1", "source_id": "s1", "root_id": "r", "publisher": "acme"},
                {"document_id": "d2", "source_id": "s2", "root_id": "r", "publisher": "acme"},
            )
        )
    )
    assert same_pub.outputs["independent_source_count"] == 1


def test_workflow_complete_is_not_answer_complete(tmp_path: Path) -> None:
    """A model-free workflow ends READY_FOR_SYNTHESIS, never COMPLETED."""
    s = build_stack(tmp_path)
    runtime = s["runtime"]
    task, plan = runtime.plan_research("what is the surface code threshold", project_id="p")
    run = runtime.start_research(plan.plan_id)
    assert run.status is RunStatus.READY_FOR_SYNTHESIS
    assert run.status is not RunStatus.COMPLETED
    # The synthesis boundary was produced (a future inference request, not an answer).
    assert run.outputs.get("synthesis_request_ready") is True


def _registry_without(capability: str) -> CapabilityRegistry:
    def cap(name: str) -> ResearchCapability:
        return ResearchCapability(
            name=name,
            description=name,
            required_permission="analyze",
            availability="unavailable" if name == capability else "available",
        )

    return CapabilityRegistry(
        {
            name: cap(name)
            for name in ("retrieval", "memory", "verification", "computation", "artifact")
        }
    )


def test_missing_verification_is_explicit_degradation(tmp_path: Path) -> None:
    """A FACT_CHECK without verification ends SYNTHESIS_REQUIRED, degraded."""
    s = build_stack(tmp_path)
    runtime = s["runtime"]
    ostore = s["orchestration_store"]
    # Rebuild orchestration with verification unavailable.
    capabilities = _registry_without("verification")
    planner = ResearchPlanner(capabilities=capabilities)
    service = OrchestrationService(
        ostore, runtime=runtime, capabilities=capabilities, planner=planner
    )

    task, plan = service.plan_research(
        "the surface code achieves a high threshold",
        project_id="p",
        task_type=TaskType.FACT_CHECK,
        profile="DEEP",
    )
    # The plan records the missing required capability explicitly.
    assert "verification" in plan.missing_capabilities

    run = service.start_research(plan.plan_id)
    assert run.status is RunStatus.SYNTHESIS_REQUIRED
    assert "verification" in run.degradation


def test_missing_computation_is_explicit_degradation(tmp_path: Path) -> None:
    """A DATA_ANALYSIS without computation ends SYNTHESIS_REQUIRED, degraded."""
    s = build_stack(tmp_path)
    runtime = s["runtime"]
    ostore = s["orchestration_store"]
    capabilities = _registry_without("computation")
    planner = ResearchPlanner(capabilities=capabilities)
    service = OrchestrationService(
        ostore, runtime=runtime, capabilities=capabilities, planner=planner
    )

    task, plan = service.plan_research(
        "analyze the data",
        project_id="p",
        task_type=TaskType.DATA_ANALYSIS,
        profile="DEEP",
    )
    assert "computation" in plan.missing_capabilities
    run = service.start_research(plan.plan_id)
    assert run.status is RunStatus.SYNTHESIS_REQUIRED
    assert "computation" in run.degradation


def test_verification_status_is_insufficient_evidence(tmp_path: Path) -> None:
    """The verification report reflects that no support was manufactured."""
    s = build_stack(tmp_path)
    runtime = s["runtime"]
    task, plan = runtime.plan_research(
        "the surface code achieves a high threshold",
        project_id="p",
        task_type=TaskType.FACT_CHECK,
        profile="DEEP",
    )
    run = runtime.start_research(plan.plan_id)
    statuses = as_str_tuple(run.outputs.get("verification_statuses"))
    assert VerificationStatus.INSUFFICIENT_EVIDENCE.value in statuses
