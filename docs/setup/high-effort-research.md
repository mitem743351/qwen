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
)
```

`run_high_effort` drives the **real** Research Runtime: it performs retrieval
via `search_corpus`, verification via `create_claim`/`verify_claim`/
`get_contradictions`, computation via `run_analysis`, and critique + synthesis
via `invoke_inference` — consuming the global budget automatically around each
call and enforcing wall-time before every operation. The `store` (a
`RunStateStore`, e.g. `SqliteRunStateStore`) persists the full logical run state
(budget + trajectories + stage progress), so a restart resumes rather than
recreates.

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
