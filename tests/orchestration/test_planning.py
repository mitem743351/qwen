"""Deterministic planner and classifier tests."""

from __future__ import annotations

import pytest

from qwen_research.domain.reasoning import DEEP, FAST, get_profile
from qwen_research.orchestration.models import ResearchTask, StageType, TaskComplexity, TaskType
from qwen_research.orchestration.planning import ResearchPlanner


def _planner() -> ResearchPlanner:
    return ResearchPlanner()


def test_explicit_task_type_wins() -> None:
    assert (
        _planner().classify_task_type("anything at all", TaskType.FACT_CHECK)
        is TaskType.FACT_CHECK
    )


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("compare X versus Y", TaskType.COMPARISON),
        ("fact check this claim", TaskType.FACT_CHECK),
        ("analyze the data in the csv", TaskType.DATA_ANALYSIS),
        ("a literature review of the field", TaskType.LITERATURE_REVIEW),
        ("write a report on X", TaskType.REPORT_GENERATION),
        ("what is the surface code", TaskType.QUESTION_ANSWERING),
        ("some unclassifiable deep question", TaskType.DEEP_RESEARCH),
    ],
)
def test_classify_task_type(description: str, expected: TaskType) -> None:
    assert _planner().classify_task_type(description) is expected


def test_complexity_follows_profile() -> None:
    assert (
        _planner().classify_complexity("x", task_type=TaskType.CUSTOM, profile_name="FAST")
        is TaskComplexity.SIMPLE
    )
    assert (
        _planner().classify_complexity("x", task_type=TaskType.CUSTOM, profile_name="EXTREME")
        is TaskComplexity.VERY_COMPLEX
    )


def test_complexity_bumps_on_signals() -> None:
    # FAST base is SIMPLE; heavy signals bump it upward.
    result = _planner().classify_complexity(
        "compare and analyze multiple comprehensive approaches across several sources?",
        task_type=TaskType.COMPARISON,
        profile_name="FAST",
    )
    assert result in (TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX)


def test_budget_scales_with_profile() -> None:
    fast = _planner().estimate_budget(FAST)
    deep = _planner().estimate_budget(DEEP)
    assert deep.retrieval_budget > fast.retrieval_budget
    assert deep.verification_budget > fast.verification_budget


def test_template_stages_for_deep_research() -> None:
    task = ResearchTask.create(
        "p", "deep research task", TaskType.DEEP_RESEARCH, TaskComplexity.COMPLEX, "DEEP"
    )
    plan = _planner().create_plan(task, profile=get_profile("DEEP"))
    types = [s.type for s in plan.stages]
    assert types[0] is StageType.CLASSIFY
    assert StageType.RETRIEVE in types
    assert StageType.SYNTHESIZE in types
    assert types[-1] is StageType.FINALIZE


def test_fact_check_has_claim_and_contradictions() -> None:
    task = ResearchTask.create(
        "p", "fact check task", TaskType.FACT_CHECK, TaskComplexity.MODERATE, "NORMAL"
    )
    plan = _planner().create_plan(task, profile=get_profile("NORMAL"))
    types = [s.type for s in plan.stages]
    assert StageType.CLAIM in types
    assert StageType.CONTRADICTIONS in types
    assert plan.requirements.needs_verification is True
    assert plan.requirements.needs_memory is False


def test_data_analysis_has_compute_and_describe() -> None:
    task = ResearchTask.create(
        "p", "data analysis task", TaskType.DATA_ANALYSIS, TaskComplexity.MODERATE, "NORMAL"
    )
    plan = _planner().create_plan(task, profile=get_profile("NORMAL"))
    types = [s.type for s in plan.stages]
    assert StageType.DESCRIBE_DATASET in types
    assert StageType.COMPUTE in types
    assert plan.requirements.needs_computation is True


def test_requirements_are_explicit() -> None:
    req = _planner().determine_requirements(TaskType.LITERATURE_REVIEW)
    assert req.needs_retrieval is True
    assert req.needs_contradiction_analysis is True
    assert req.needs_computation is False
