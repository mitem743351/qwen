# Enabling research workflows

Research orchestration is enabled by configuring an **orchestration database**.
Workflows are deterministic and local — no model invocation.

---

## Environment variables

| Variable | Meaning |
|----------|---------|
| `QWEN_RESEARCH_CORPUS_DB` / `CORPUS_ROOT` | corpus (for the retrieval stage) |
| `QWEN_RESEARCH_VECTOR_DB` | optional semantic/hybrid retrieval |
| `QWEN_RESEARCH_MEMORY_DB` | memory (for the memory stage) |
| `QWEN_RESEARCH_VERIFICATION_DB` | verification (for assess/verify stages) |
| `QWEN_RESEARCH_COMPUTATION_DB` | computation (for compute stages) |
| `QWEN_RESEARCH_ORCHESTRATION_DB` | orchestration (plans, runs, events) |
| `QWEN_RESEARCH_ENABLE_WRITE` | `"1"` to enable WRITE tools |

With `QWEN_RESEARCH_ORCHESTRATION_DB` set, seven tools become available:

```text
plan_research         ANALYZE   classify + plan a task (deterministic)
start_research        ANALYZE   create + execute a workflow run
get_research_status   READ      run status/progress/degradation
pause_research        ANALYZE   pause a run
resume_research       ANALYZE   resume a paused run
cancel_research       ANALYZE   cancel a run
get_research_summary  READ      bounded research summary
```

---

## Example (Qwen Studio MCP config)

```json
{
  "mcpServers": {
    "qwen-research": {
      "command": "python",
      "args": ["-m", "qwen_research.mcp"],
      "cwd": "/path/to/qwen-research-system",
      "env": {
        "QWEN_RESEARCH_CORPUS_DB": "/path/to/data/corpus.db",
        "QWEN_RESEARCH_CORPUS_ROOT": "/path/to/research/papers",
        "QWEN_RESEARCH_MEMORY_DB": "/path/to/data/memory.db",
        "QWEN_RESEARCH_VERIFICATION_DB": "/path/to/data/verification.db",
        "QWEN_RESEARCH_COMPUTATION_DB": "/path/to/data/computation.db",
        "QWEN_RESEARCH_ORCHESTRATION_DB": "/path/to/data/orchestration.db",
        "QWEN_RESEARCH_ENABLE_WRITE": "1"
      }
    }
  }
}
```

---

## Typical flow

```text
plan_research("what is the surface code threshold", project_id="p")
  → plan_id + task metadata + stages + requirements
start_research(plan_id)
  → run executes retrieve → assess → verify → … → synthesize → finalize
get_research_status(run_id)    → status/progress/degradation
get_research_summary(run_id)   → claims/evidence/contradictions/computation
```

Workflows run **synchronously** (no background worker); pause/resume/cancel
operate on persisted run state and are exercised at the engine level.

---

## Limitations

- Planning is **rule-based**; it does not understand deep natural-language intent.
- No model invocation: the synthesis step produces a `SynthesisRequest`
  boundary for a future inference runtime.
- No parallel model trajectories, no remote/distributed execution.

See [`../architecture/orchestration.md`](../architecture/orchestration.md).
