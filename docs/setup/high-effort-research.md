# High-Effort Research (Phase 10)

Enabling bounded XHIGH/EXTREME execution via GATEWAY_INFERENCE.

---

## API

```python
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.research.budget_store import SqliteBudgetStore
from qwen_research.domain.test_time import TrajectoryStrategy

runtime = InMemoryResearchRuntime(inference=...)

store = SqliteBudgetStore("budgets.db")
store.initialize()

result = runtime.run_high_effort(
    profile="XHIGH",
    store=store,
    run_id="run-1",            # stable across restarts
    task_description="surface-code threshold",
    trajectory_strategies=(TrajectoryStrategy.DIRECT, TrajectoryStrategy.COUNTERARGUMENT),
    stages=my_stages,          # performs the bounded workflow work
)
```

`stages` receives a `HighEffortContext` and must `reserve`/`commit` budget for
each unit of work it performs. The budget is loaded (resume) or allocated
(fresh) from the store, and persisted after the run — so a restart never resets
consumed resources.

---

## Profiles

`FAST`, `NORMAL`, `DEEP`, `XHIGH`, `EXTREME` each have explicit numeric
ceilings (see [`../architecture/test-time-scaling.md`](../architecture/test-time-scaling.md)).
XHIGH/EXTREME never grant more permissions.

## Native reasoning

Native Qwen reasoning control is translated per model/endpoint
(`reasoning_effort` XOR `thinking_budget`), never fabricated.

## Live test (opt-in)

```text
QWEN_LIVE_TEST=1 DASHSCOPE_API_KEY=... pytest tests/inference/test_live.py
```

Never required for CI.
