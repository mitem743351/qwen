"""Reasoning profile and budget contracts."""

from __future__ import annotations

import pytest

from qwen_research.domain.errors import ValidationError
from qwen_research.domain.reasoning import (
    DEEP,
    EXTREME,
    FAST,
    NORMAL,
    XHIGH,
    ParallelismMode,
    ReasoningProfile,
)


def test_profile_names() -> None:
    assert {p.name for p in (FAST, NORMAL, DEEP, XHIGH, EXTREME)} == {
        "FAST",
        "NORMAL",
        "DEEP",
        "XHIGH",
        "EXTREME",
    }


def test_profiles_are_distinct_policies() -> None:
    # Profiles are workflow dials, not provider parameters.
    assert FAST.critique_passes < DEEP.critique_passes < EXTREME.critique_passes
    assert FAST.verification_passes < DEEP.verification_passes < EXTREME.verification_passes
    assert FAST.parallelism is ParallelismMode.OFF
    assert EXTREME.parallelism is ParallelismMode.EXPECTED


def test_profile_validation_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        ReasoningProfile(
            name="BAD",
            planning_depth=-1,
            retrieval_depth=0,
            evidence_threshold="low",
            independent_attempts=1,
            critique_passes=0,
            verification_passes=0,
            context_budget=1,
            output_budget=1,
            continuation_policy=FAST.continuation_policy,
            parallelism=ParallelismMode.OFF,
        )


def test_profile_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ReasoningProfile(
            name="",
            planning_depth=0,
            retrieval_depth=0,
            evidence_threshold="low",
            independent_attempts=1,
            critique_passes=0,
            verification_passes=0,
            context_budget=1,
            output_budget=1,
            continuation_policy=FAST.continuation_policy,
            parallelism=ParallelismMode.OFF,
        )


def test_budget_is_derived_from_profile() -> None:
    budget = DEEP.budget()
    assert budget.context_budget == DEEP.context_budget
    assert budget.verification_budget == DEEP.verification_passes
    assert budget.output_budget == DEEP.output_budget
    # Budgets are indicative allocations, not enforced limits.
    assert isinstance(budget.inference_budget, int)


def test_extreme_is_a_resource_profile() -> None:
    # EXTREME allocates more across the resource dimensions than DEEP.
    assert EXTREME.budget().context_budget > DEEP.budget().context_budget
    assert EXTREME.budget().verification_budget > DEEP.budget().verification_budget
