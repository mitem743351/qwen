"""Adaptive test-time budget scheduler (Phase 10).

Reallocates *remaining* (never consumed) budget across workflow dimensions
according to explicit, deterministic rules. Invariants:

1. Never exceeds global ceilings (allocated is authoritative).
2. Never makes a consumed budget available again (consumed is monotonic).
3. Reallocation is observable (recorded decisions).
4. Reallocation is deterministic / policy-driven (never model-driven).
5. Restart preserves consumed budget (the budget object, not the scheduler).
6. The model cannot increase budget.
"""

from __future__ import annotations

import dataclasses

from qwen_research.common.serialization import serializable
from qwen_research.domain.test_time import ResourceDimension, TestTimeComputeBudget


@serializable
@dataclasses.dataclass(frozen=True)
class ReallocationDecision:
    """A recorded reallocation of *remaining* budget between dimensions."""

    from_dimension: ResourceDimension
    to_dimension: ResourceDimension
    amount: float
    reason: str


@serializable
@dataclasses.dataclass(frozen=True)
class BudgetSignal:
    """An observable signal the scheduler may act on (never the model's request)."""

    dimension: ResourceDimension
    strength: str  # "weak" | "strong"
    reason: str


class TestTimeScheduler:
    """Deterministic reallocation of remaining budget based on signals."""

    __test__ = False  # not a pytest test class

    def __init__(self, budget: TestTimeComputeBudget) -> None:
        self._budget = budget
        self._decisions: list[ReallocationDecision] = []

    @property
    def budget(self) -> TestTimeComputeBudget:
        return self._budget

    @property
    def decisions(self) -> tuple[ReallocationDecision, ...]:
        return tuple(self._decisions)

    def reallocate(
        self,
        from_dimension: ResourceDimension,
        to_dimension: ResourceDimension,
        amount: float,
        reason: str,
    ) -> bool:
        """Move *amount* of *remaining* budget from one dimension to another.

        Only reallocates the *free* remainder (never reserved/consumed), caps at
        what is actually available, and never exceeds the target allocation.
        """
        if amount <= 0:
            return False
        available = self._budget.remaining(from_dimension)
        transfer = min(amount, available)
        if transfer <= 0:
            return False

        # Decrease source allocation (only the free remainder moves).
        self._budget.allocated[from_dimension] -= transfer
        # Increase target allocation, capped at the original ceiling is
        # implicit — remaining is still bounded by allocated.
        self._budget.allocated[to_dimension] = (
            self._budget.allocated.get(to_dimension, 0.0) + transfer
        )
        self._decisions.append(
            ReallocationDecision(
                from_dimension=from_dimension,
                to_dimension=to_dimension,
                amount=transfer,
                reason=reason,
            )
        )
        return True

    def apply_signal(self, signal: BudgetSignal) -> None:
        """Apply a policy-driven reallocation for a common signal.

        ``weak`` evidence → more retrieval; ``strong`` evidence → shift budget
        toward verification. Deterministic and bounded — a signal never creates
        budget.
        """
        if signal.dimension is ResourceDimension.RETRIEVAL_ROUNDS and signal.strength == "weak":
            self.reallocate(
                ResourceDimension.CRITIQUE_ROUNDS,
                ResourceDimension.RETRIEVAL_ROUNDS,
                1.0,
                signal.reason or "weak evidence: increase retrieval",
            )
        elif (
            signal.dimension is ResourceDimension.VERIFICATION_ROUNDS
            and signal.strength == "strong"
        ):
            self.reallocate(
                ResourceDimension.CRITIQUE_ROUNDS,
                ResourceDimension.VERIFICATION_ROUNDS,
                1.0,
                signal.reason or "contradiction found: increase verification",
            )


class BudgetMeter:
    """A lightweight, observable meter over a single dimension."""

    def __init__(self, budget: TestTimeComputeBudget, dimension: ResourceDimension) -> None:
        self._budget = budget
        self._dimension = dimension

    def reserve(self, amount: float = 1.0) -> bool:
        return self._budget.reserve(self._dimension, amount)

    def commit(self, amount: float = 1.0) -> None:
        self._budget.commit(self._dimension, amount)

    def remaining(self) -> float:
        return self._budget.remaining(self._dimension)

    def exhausted(self) -> bool:
        return self._budget.exhausted(self._dimension)


def make_budget_meters(
    budget: TestTimeComputeBudget,
) -> dict[ResourceDimension, BudgetMeter]:
    return {d: BudgetMeter(budget, d) for d in budget.allocated}
