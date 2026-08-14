"""Reasoning profiles and budgets.

A ``ReasoningProfile`` is an abstract **workflow/resource policy**, never a set
of provider parameters. It does not guarantee a specific model reasoning budget
unless the active inference owner/provider exposes the required controls (see
``docs/architecture/reasoning-engine.md``). ``ReasoningBudget`` is the
resource-allocation facet of a profile — a data object only; budgets are not
executed or enforced in Phase 1.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import TYPE_CHECKING

from qwen_research.common.serialization import serializable
from qwen_research.domain.errors import ValidationError

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from qwen_research.domain.inference import InferencePolicy


class ContinuationPolicy(StrEnum):
    """How long outputs are continued."""

    NONE = "none"
    SECTIONED = "sectioned"
    CONTINUE = "continue"
    ARTIFACT_FIRST = "artifact_first"


class ParallelismMode(StrEnum):
    """Whether parallel trajectories are permitted."""

    OFF = "off"
    OPTIONAL = "optional"
    EXPECTED = "expected"


@serializable
@dataclasses.dataclass(frozen=True)
class ReasoningProfile:
    """An abstract resource-allocation and workflow policy."""

    name: str
    planning_depth: int
    retrieval_depth: int
    evidence_threshold: str
    independent_attempts: int
    critique_passes: int
    verification_passes: int
    context_budget: int
    output_budget: int
    continuation_policy: ContinuationPolicy
    parallelism: ParallelismMode

    def __post_init__(self) -> None:
        if not self.name:
            raise ValidationError("profile name must not be empty")
        for field, value in (
            ("planning_depth", self.planning_depth),
            ("retrieval_depth", self.retrieval_depth),
            ("independent_attempts", self.independent_attempts),
            ("critique_passes", self.critique_passes),
            ("verification_passes", self.verification_passes),
            ("context_budget", self.context_budget),
            ("output_budget", self.output_budget),
        ):
            if value < 0:
                raise ValidationError(f"{field} must be non-negative, got {value}")

    def budget(self) -> ReasoningBudget:
        """Derive the resource budget implied by this profile.

        Budgets are indicative allocations, not enforced limits.
        """
        return ReasoningBudget(
            inference_budget=self.independent_attempts * max(1, self.verification_passes + 1),
            retrieval_budget=self.retrieval_depth + 1,
            tool_budget=self.critique_passes + self.verification_passes + 1,
            context_budget=self.context_budget,
            verification_budget=self.verification_passes,
            output_budget=self.output_budget,
            time_budget=None,
            parallelism_budget=0 if self.parallelism is ParallelismMode.OFF else 1,
        )

    def inference_policy(self) -> InferencePolicy:
        """Express this profile's intents as a provider-neutral ``InferencePolicy``.

        Maps the profile's workflow dials onto capability-aligned intents. It
        does **not** claim provider-native reasoning control: the resulting
        policy *requests* reasoning effort and a reasoning budget, which
        capability negotiation then resolves to native support or workflow
        emulation (Phase 1.2). No provider parameter is produced here.
        """
        from qwen_research.domain.inference import InferencePolicy

        budget = self.budget()
        return InferencePolicy(
            reasoning=True,
            reasoning_budget=budget.inference_budget,
            max_output_tokens=budget.output_budget,
            parallel_generation=budget.parallelism_budget > 0,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class ReasoningBudget:
    """A resource-policy object describing allocations for a reasoning effort."""

    inference_budget: int
    retrieval_budget: int
    tool_budget: int
    context_budget: int
    verification_budget: int
    output_budget: int
    time_budget: float | None = None
    parallelism_budget: int = 0


#: Built-in profiles (Phase 0.5 / architecture §5).
FAST = ReasoningProfile(
    name="FAST",
    planning_depth=0,
    retrieval_depth=0,
    evidence_threshold="low",
    independent_attempts=1,
    critique_passes=0,
    verification_passes=0,
    context_budget=1,
    output_budget=1,
    continuation_policy=ContinuationPolicy.NONE,
    parallelism=ParallelismMode.OFF,
)

NORMAL = ReasoningProfile(
    name="NORMAL",
    planning_depth=1,
    retrieval_depth=1,
    evidence_threshold="medium",
    independent_attempts=1,
    critique_passes=1,
    verification_passes=1,
    context_budget=2,
    output_budget=2,
    continuation_policy=ContinuationPolicy.SECTIONED,
    parallelism=ParallelismMode.OFF,
)

DEEP = ReasoningProfile(
    name="DEEP",
    planning_depth=2,
    retrieval_depth=2,
    evidence_threshold="high",
    independent_attempts=2,
    critique_passes=2,
    verification_passes=2,
    context_budget=4,
    output_budget=4,
    continuation_policy=ContinuationPolicy.SECTIONED,
    parallelism=ParallelismMode.OFF,
)

XHIGH = ReasoningProfile(
    name="XHIGH",
    planning_depth=3,
    retrieval_depth=3,
    evidence_threshold="high",
    independent_attempts=3,
    critique_passes=3,
    verification_passes=3,
    context_budget=8,
    output_budget=8,
    continuation_policy=ContinuationPolicy.CONTINUE,
    parallelism=ParallelismMode.OPTIONAL,
)

EXTREME = ReasoningProfile(
    name="EXTREME",
    planning_depth=4,
    retrieval_depth=4,
    evidence_threshold="very_high",
    independent_attempts=4,
    critique_passes=4,
    verification_passes=4,
    context_budget=16,
    output_budget=16,
    continuation_policy=ContinuationPolicy.CONTINUE,
    parallelism=ParallelismMode.EXPECTED,
)
