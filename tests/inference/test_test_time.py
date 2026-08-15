"""Phase 10 test-time compute budget, scheduler, and profile tests."""

from __future__ import annotations

from typing import Any

import pytest

from qwen_research.domain.errors import ValidationError
from qwen_research.domain.test_time import (
    PROFILE_POLICIES,
    ResourceDimension,
    get_test_time_policy,
)
from qwen_research.research.budget_store import InMemoryBudgetStore, SqliteBudgetStore
from qwen_research.research.scheduler import BudgetSignal, TestTimeScheduler


def test_profiles_have_explicit_finite_ceilings() -> None:
    for name in ("FAST", "NORMAL", "DEEP", "XHIGH", "EXTREME"):
        policy = get_test_time_policy(name)
        assert policy.max_inference_calls > 0
        assert policy.max_tool_calls > 0
        assert policy.max_trajectory_count > 0
        assert policy.max_wall_time_seconds > 0
        assert policy.max_total_tokens > 0


def test_high_effort_profiles_have_larger_workflow_budgets() -> None:
    extreme = get_test_time_policy("EXTREME").max_tool_calls
    xhigh = get_test_time_policy("XHIGH").max_tool_calls
    deep = get_test_time_policy("DEEP").max_tool_calls
    assert extreme > xhigh > deep
    assert get_test_time_policy("XHIGH").max_trajectory_count == 3
    assert get_test_time_policy("EXTREME").max_trajectory_count == 5


def test_xhigh_native_reasoning_hint() -> None:
    assert get_test_time_policy("XHIGH").native_reasoning == "reasoning_effort:xhigh"
    assert get_test_time_policy("EXTREME").native_reasoning == "reasoning_effort:xhigh"
    # Lower profiles request no native depth control.
    assert get_test_time_policy("DEEP").native_reasoning == ""


def test_budget_reserve_commit_remaining() -> None:
    budget = get_test_time_policy("NORMAL").budget()
    assert budget.can_afford(ResourceDimension.TOOL_CALLS, 16)
    assert budget.reserve(ResourceDimension.TOOL_CALLS, 10)
    assert budget.remaining(ResourceDimension.TOOL_CALLS) == 6
    budget.commit(ResourceDimension.TOOL_CALLS, 10)
    assert budget.consumed_for(ResourceDimension.TOOL_CALLS) == 10
    assert budget.remaining(ResourceDimension.TOOL_CALLS) == 6


def test_budget_cannot_overshoot_allocation() -> None:
    budget = get_test_time_policy("FAST").budget()
    # max_tool_calls = 4; reserve 4 then try a 5th.
    assert budget.reserve(ResourceDimension.TOOL_CALLS, 4)
    assert not budget.reserve(ResourceDimension.TOOL_CALLS, 1)
    assert budget.consumed_for(ResourceDimension.TOOL_CALLS) == 0  # reservation not committed
    assert budget.remaining(ResourceDimension.TOOL_CALLS) == 0


def test_consumed_is_monotonic() -> None:
    budget = get_test_time_policy("NORMAL").budget()
    budget.commit(ResourceDimension.TOKENS, 1000)
    budget.commit(ResourceDimension.TOKENS, 500)
    assert budget.consumed_for(ResourceDimension.TOKENS) == 1500


def test_budget_restart_does_not_reset(tmp_path: Any) -> None:
    store = SqliteBudgetStore(tmp_path / "budgets.db")
    store.initialize()
    budget = get_test_time_policy("XHIGH").budget()
    budget.commit(ResourceDimension.TOOL_CALLS, 30)
    budget.commit(ResourceDimension.RETRIEVAL_ROUNDS, 2)
    store.save("run-1", budget)

    # "Restart": load from the store.
    resumed = store.load("run-1")
    assert resumed is not None
    assert resumed.consumed_for(ResourceDimension.TOOL_CALLS) == 30
    assert resumed.consumed_for(ResourceDimension.RETRIEVAL_ROUNDS) == 2


def test_in_memory_store_roundtrip() -> None:
    store = InMemoryBudgetStore()
    budget = get_test_time_policy("DEEP").budget()
    budget.commit(ResourceDimension.VERIFICATION_ROUNDS, 1)
    store.save("run-1", budget)
    loaded = store.load("run-1")
    assert loaded is not None
    assert loaded.consumed_for(ResourceDimension.VERIFICATION_ROUNDS) == 1


def test_scheduler_reallocates_remaining_only() -> None:
    budget = get_test_time_policy("NORMAL").budget()
    scheduler = TestTimeScheduler(budget)
    # NORMAL has 2 retrieval rounds, 1 critique round. Consume 1 retrieval.
    budget.commit(ResourceDimension.RETRIEVAL_ROUNDS, 1)
    scheduler.apply_signal(
        BudgetSignal(ResourceDimension.RETRIEVAL_ROUNDS, "weak", "weak evidence")
    )
    # A critique round (remaining 1) moved to retrieval.
    assert len(scheduler.decisions) == 1
    assert budget.remaining(ResourceDimension.RETRIEVAL_ROUNDS) == 2  # 1 free + 1 reallocated
    # Consumed budget is never made available again.
    assert budget.consumed_for(ResourceDimension.RETRIEVAL_ROUNDS) == 1


def test_scheduler_never_exceeds_global_ceiling() -> None:
    budget = get_test_time_policy("FAST").budget()
    scheduler = TestTimeScheduler(budget)
    # FAST has 0 critique rounds; reallocation source is empty → no-op.
    scheduler.apply_signal(
        BudgetSignal(ResourceDimension.RETRIEVAL_ROUNDS, "weak", "weak evidence")
    )
    # No budget was created out of nothing.
    total_retrieval = budget.remaining(ResourceDimension.RETRIEVAL_ROUNDS)
    assert total_retrieval <= get_test_time_policy("FAST").max_retrieval_rounds


def test_unknown_profile_rejected() -> None:
    with pytest.raises(ValidationError):
        get_test_time_policy("BOGUS")


def test_profile_policy_names_match_reasoning_profiles() -> None:
    from qwen_research.domain.reasoning import PROFILES

    assert set(PROFILE_POLICIES) == set(PROFILES)
