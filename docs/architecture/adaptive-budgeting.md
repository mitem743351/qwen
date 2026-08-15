# Adaptive Budgeting (Phase 10)

`TestTimeScheduler` reallocates *remaining* budget between workflow dimensions
in response to observable signals — deterministically and observably, never on
the model's request.

## Rules

1. Never exceed global ceilings.
2. Never make a consumed budget available again.
3. Reallocation is observable (recorded `ReallocationDecision`s).
4. Reallocation is deterministic / policy-driven.
5. Restart preserves consumed budget.
6. The model cannot increase budget.

## Signals

`BudgetSignal(dimension, strength, reason)`:

- `RETRIEVAL_ROUNDS` + `weak` → move a critique round to retrieval (weak
  evidence).
- `VERIFICATION_ROUNDS` + `strong` → move a critique round to verification
  (contradiction found).

## Early stopping

Budget remaining is not a requirement to spend it. `HighEffortContext.should_continue()`
returns False when the wall-time or the whole budget is exhausted, and the
scheduler never escalates merely because the model requests more work.

See [`test-time-scaling.md`](test-time-scaling.md).
