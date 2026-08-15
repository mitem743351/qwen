# Enabling deterministic computation

The computation layer is enabled by configuring a **computation database**
alongside a corpus (datasets resolve through the corpus security layer). It is
deterministic and local — DuckDB analytics plus a subprocess-isolated Python
sandbox.

---

## Environment variables

| Variable | Meaning |
|----------|---------|
| `QWEN_RESEARCH_CORPUS_DB` | SQLite corpus index (required for dataset resolution) |
| `QWEN_RESEARCH_CORPUS_ROOT` | allowlisted corpus directory (holds the datasets) |
| `QWEN_RESEARCH_COMPUTATION_DB` | SQLite computation metadata store |
| `QWEN_RESEARCH_WORKSPACE_ROOT` | output root for computation artifacts (default `workspaces/computation`) |
| `QWEN_RESEARCH_ENABLE_WRITE` | `"1"` to enable WRITE tools (also unlocks `analyze`) |

With `QWEN_RESEARCH_COMPUTATION_DB` set, five tools become available:

```text
describe_dataset         READ      profile a dataset (schema/statistics/preview)
run_query                ANALYZE   validated, parameterized SQL over approved datasets
run_analysis             ANALYZE   structured operations (statistics/group/aggregate/…)
get_computation_result   READ      read a persisted result by id
run_python               EXECUTE   sandboxed Python (disabled by default)
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
        "QWEN_RESEARCH_CORPUS_ROOT": "/path/to/research/data",
        "QWEN_RESEARCH_COMPUTATION_DB": "/path/to/data/computation.db",
        "QWEN_RESEARCH_WORKSPACE_ROOT": "/path/to/data/workspace",
        "QWEN_RESEARCH_ENABLE_WRITE": "1"
      }
    }
  }
}
```

---

## Typical flow

```text
describe_dataset({root_id, relative_path})        → schema + statistics
run_analysis(operation="statistics", column=…)    → ComputationResult (values)
run_query("SELECT … FROM t0 WHERE …", params)     → ComputationResult (table)
run_analysis(operation="simulate", seed=…)        → summary + artifact
get_computation_result(computation_id)            → status/result/artifacts/provenance
```

Results survive restart (persisted in the computation store); large results
become artifacts in the workspace root rather than giant MCP payloads.

---

## Limitations

- The Python sandbox is a restricted execution environment, **not** a hardened
  security boundary (see [`../architecture/python-sandbox.md`](../architecture/python-sandbox.md)).
- Memory limits are best-effort (POSIX only).
- No Rust/GPU/remote backends; no arbitrary shell or filesystem access.

See [`../architecture/computation.md`](../architecture/computation.md).
