# Tool-Execution Reliability (Phase 9.4)

Enabling durable, crash-safe tool execution for the gateway tool loop.

---

## Configuration

`ToolLoopConfig` (in `research/tool_loop.py`) controls the reliability layer:

| Field | Default | Meaning |
|-------|---------|---------|
| `lease_duration_seconds` | `120.0` | Tool-execution claim lease duration |
| `recovery_policy` | `"reclaim_stale_if_safe"` | Stale-claim recovery (`reclaim_stale_if_safe` / `fail_on_unknown`) |

A `ToolExecutionStore` is passed to `run_tool_loop(..., store=…)`. The
`SqliteToolExecutionStore` (path-based, restart-safe) and
`InMemoryToolExecutionStore` (tests) are provided.

```python
from qwen_research.research.tool_store import SqliteToolExecutionStore
from qwen_research.research.tool_loop import run_tool_loop

store = SqliteToolExecutionStore("tool_exec.db")
store.initialize()
result = run_tool_loop(
    request,
    invoke=runtime.invoke_inference,
    tools=runtime.model_tool_registry(),
    profile=ANALYSIS,
    store=store,
    inference_session_id="inf_session_…",  # stable across restarts
)
```

The `inference_session_id` is the stable identity; a workflow restart reusing it
replays completed tool results instead of re-executing.

---

## Tool semantics

A tool may declare `execution_semantics` (`READ_ONLY`, `IDEMPOTENT`,
`SIDE_EFFECTING`, `DESTRUCTIVE`, `UNKNOWN`). When absent, semantics default from
the tool's permission class:

```text
READ / ANALYZE → READ_ONLY / IDEMPOTENT
WRITE / EXECUTE → SIDE_EFFECTING
DESTRUCTIVE    → DESTRUCTIVE
```

Side-effecting tools are never auto-retried after a crash-ambiguous outcome
(`UNKNOWN`); read-only/idempotent tools may be safely reclaimed.

---

## Guarantee

At-most-once after durable completion; crash-ambiguous outcomes are `UNKNOWN`
(never silently duplicated, never replayed as success).

See [`../architecture/tool-execution-reliability.md`](../architecture/tool-execution-reliability.md).
