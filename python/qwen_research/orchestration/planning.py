"""Deterministic research planner and classifier.

Phase 7 planning is **rule-based**: it classifies tasks, estimates complexity,
selects a workflow template, and derives requirements/budget without invoking a
model. A future model-assisted planner will sit behind the same
:class:`ResearchPlanner` interface.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

from qwen_research.domain.reasoning import ReasoningBudget, ReasoningProfile, get_profile
from qwen_research.orchestration.models import (
    ComputationSpec,
    PlanRequirements,
    ResearchPlan,
    ResearchStage,
    ResearchTask,
    TaskComplexity,
    TaskType,
)
from qwen_research.orchestration.templates import template_for

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from qwen_research.orchestration.capabilities import CapabilityRegistry

#: Keyword → task-type signals (deterministic routing heuristic).
_TYPE_KEYWORDS: dict[TaskType, tuple[str, ...]] = {
    TaskType.COMPARISON: ("compare", "versus", " vs ", "difference between", "contrast"),
    TaskType.FACT_CHECK: (
        "fact check", "fact-check", "is it true", "verify the claim", "true or false"
    ),
    TaskType.DATA_ANALYSIS: (
        "analyze the data", "dataset", "data analysis", "csv",
        "statistics of", "run analysis",
    ),
    TaskType.LITERATURE_REVIEW: (
        "literature review", "survey of", "review of the literature",
        "state of the art",
    ),
    TaskType.REPORT_GENERATION: ("write a report", "report on", "generate a report"),
    TaskType.SYNTHESIS: ("synthesize", "synthesis", "summarize the findings"),
    TaskType.QUESTION_ANSWERING: ("what is", "how does", "why", "explain", "who is"),
}

#: Complexity signal keywords (bump the heuristic).
_COMPLEXITY_SIGNALS: tuple[str, ...] = (
    "compare", "analyze", "evaluate", "multi", "comprehensive", "across",
    "several", "multiple", "deep", "contradict", "verify",
)

_COMPLEXITY_BY_PROFILE: dict[str, TaskComplexity] = {
    "FAST": TaskComplexity.SIMPLE,
    "NORMAL": TaskComplexity.MODERATE,
    "DEEP": TaskComplexity.COMPLEX,
    "XHIGH": TaskComplexity.VERY_COMPLEX,
    "EXTREME": TaskComplexity.VERY_COMPLEX,
}

_ORDER: tuple[TaskComplexity, ...] = (
    TaskComplexity.SIMPLE,
    TaskComplexity.MODERATE,
    TaskComplexity.COMPLEX,
    TaskComplexity.VERY_COMPLEX,
)


class ResearchPlanner:
    """Deterministic planner: classify, plan, budget, requirements."""

    def __init__(self, *, capabilities: CapabilityRegistry | None = None) -> None:
        self._capabilities = capabilities

    # -- classification ----------------------------------------------------

    def classify_task_type(self, description: str, explicit: TaskType | None = None) -> TaskType:
        """Classify the task type deterministically (explicit value wins)."""
        if explicit is not None:
            return explicit
        lowered = description.lower()
        for task_type in (
            TaskType.FACT_CHECK,
            TaskType.DATA_ANALYSIS,
            TaskType.LITERATURE_REVIEW,
            TaskType.REPORT_GENERATION,
            TaskType.SYNTHESIS,
            TaskType.COMPARISON,
            TaskType.QUESTION_ANSWERING,
        ):
            if any(keyword in lowered for keyword in _TYPE_KEYWORDS[task_type]):
                return task_type
        return TaskType.DEEP_RESEARCH

    def classify_complexity(
        self,
        description: str,
        *,
        task_type: TaskType,
        profile_name: str,
    ) -> TaskComplexity:
        """Return a routing-heuristic complexity (never a true-difficulty claim)."""
        base = _COMPLEXITY_BY_PROFILE.get(profile_name, TaskComplexity.MODERATE)
        index = _ORDER.index(base)
        lowered = description.lower()
        bumps = sum(1 for signal in _COMPLEXITY_SIGNALS if signal in lowered)
        # Subquestion count (question marks) also nudges complexity upward.
        bumps += min(2, lowered.count("?"))
        if task_type in (TaskType.COMPARISON, TaskType.TECHNICAL_ANALYSIS, TaskType.DEEP_RESEARCH):
            bumps += 1
        index = min(len(_ORDER) - 1, index + bumps)
        return _ORDER[index]

    # -- budgeting ---------------------------------------------------------

    def estimate_budget(self, profile: ReasoningProfile) -> ReasoningBudget:
        """Derive the workflow resource budget from a reasoning profile.

        Higher profiles receive larger orchestration budgets (retrieval,
        verification, computation, parallelism). These are orchestration
        allocations, not model-token budgets.
        """
        base = profile.budget()
        multiplier = 1 + profile.retrieval_depth
        return ReasoningBudget(
            inference_budget=base.inference_budget,
            retrieval_budget=base.retrieval_budget * multiplier,
            tool_budget=base.tool_budget,
            context_budget=base.context_budget,
            verification_budget=base.verification_budget * multiplier,
            output_budget=base.output_budget,
            time_budget=base.time_budget,
            parallelism_budget=base.parallelism_budget,
        )

    # -- requirements ------------------------------------------------------

    def determine_requirements(self, task_type: TaskType) -> PlanRequirements:
        """Return the explicit capability requirements for *task_type*."""
        _, requirements, _ = template_for(task_type)
        return requirements

    # -- planning ----------------------------------------------------------

    def create_plan(
        self,
        task: ResearchTask,
        *,
        profile: ReasoningProfile | None = None,
        subquestions: tuple[str, ...] = (),
        computation: ComputationSpec | None = None,
    ) -> ResearchPlan:
        """Build a deterministic plan for a classified task."""
        stages, requirements, criteria = template_for(task.task_type)
        profile = profile or get_profile(task.reasoning_profile)
        budget = self.estimate_budget(profile)

        # Drop capability-gated stages that are unavailable at plan time and
        # record the *required* missing capabilities explicitly (so the run is
        # degraded, never silently "complete").
        stages = self._filter_unavailable(stages)
        missing = self._missing_capabilities(requirements)

        return ResearchPlan.create(
            task.task_id,
            task.description,
            stages,
            subquestions=subquestions or (task.description,),
            requirements=requirements,
            completion_criteria=criteria,
            budget=budget,
            computation=computation,
            missing_capabilities=missing,
        )

    def _missing_capabilities(self, requirements: PlanRequirements) -> tuple[str, ...]:
        """Return the required capabilities that are unavailable.

        This is what turns a missing capability into an explicit degradation
        on the run (via ``ResearchPlan.missing_capabilities``), rather than a
        silent drop.
        """
        if self._capabilities is None:
            return ()
        needed = (
            ("retrieval", requirements.needs_retrieval),
            (
                "verification",
                requirements.needs_verification or requirements.needs_contradiction_analysis,
            ),
            ("computation", requirements.needs_computation),
            ("memory", requirements.needs_memory),
            ("artifact", requirements.needs_artifacts),
        )
        return tuple(
            name
            for name, is_needed in needed
            if is_needed and not self._capabilities.available(name)
        )

    def _filter_unavailable(
        self,
        stages: tuple[ResearchStage, ...],
    ) -> tuple[ResearchStage, ...]:
        if self._capabilities is None:
            return stages
        kept: list[ResearchStage] = []
        dropped: set[str] = set()
        for stage in stages:
            capability = _stage_capability(stage)
            if capability is not None and not self._capabilities.available(capability):
                dropped.add(stage.stage_id)
                continue
            kept.append(stage)
        # Remove dangling dependencies on dropped stages so downstream stages
        # do not wait forever for a removed capability.
        return tuple(
            dataclasses.replace(
                stage,
                dependencies=tuple(d for d in stage.dependencies if d not in dropped),
            )
            for stage in kept
        )


def _stage_capability(stage: ResearchStage) -> str | None:
    """Map a stage type to the capability it requires (None = deterministic).

    ``ASSESS_EVIDENCE`` (mark candidate evidence) and ``CORROBORATE`` (source
    independence over retrieval metadata) are deterministic Phase-7 operations
    and need no external service.
    """
    from qwen_research.orchestration.models import StageType

    return {
        StageType.RETRIEVE: "retrieval",
        StageType.CLAIM: "verification",
        StageType.VERIFY: "verification",
        StageType.CONTRADICTIONS: "verification",
        StageType.DESCRIBE_DATASET: "computation",
        StageType.COMPUTE: "computation",
        StageType.MEMORY: "memory",
    }.get(stage.type)


def split_subquestions(description: str) -> tuple[str, ...]:
    """Split a description into a coarse set of subquestions (deterministic).

    Used only to seed retrieval queries; never a claim of semantic intent.
    """
    parts = [p.strip() for p in re.split(r"[?.;]", description) if p.strip()]
    return tuple(parts or [description])
