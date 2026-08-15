# Deterministic Computation

Phase 6 introduces the deterministic computation layer: bounded, provenance-bearing
numerical analysis, structured-data analysis, transformations, simulations, and
reproducible calculations. The model **proposes and interprets**; the runtime
**computes**.

> **Core principle:** model reasoning ≠ deterministic computation. A
> computation result is not a claim and not verified truth — a deterministic
> calculation can still be based on incorrect inputs.

Module: `python/qwen_research/computation/`.

---

## Target path

```text
Qwen Studio → MCP → Research Runtime → Computation Runtime
    ├── DuckDB analytics
    └── Python sandbox
    → ComputationResult (values / statistics / artifacts / provenance)
    → Verification / ResearchContext → Qwen
```

---

## Domain model

| Object | Purpose |
|--------|---------|
| `ComputationRequest` | computation_id, project_id, task_id, session_id, operation, input_refs, parameters, execution_profile, requested_output, created_at |
| `ComputationResult` | computation_id, status, operation, result_type, value, rows, metrics, artifact_refs, provenance, runtime_metadata, started_at, completed_at |
| `DatasetReference` | a controlled reference (root_id/relative_path/document_id/dataset_id/artifact_id/format) — never an arbitrary OS path |
| `DatasetProfile` | row/column counts, per-column profile, size, content hash, missing/duplicate counts |
| `ComputationSummary` | a bounded, context-safe summary for `ResearchContext` |

### Statuses

`CREATED · VALIDATING · RUNNING · COMPLETED · FAILED · TIMED_OUT ·
RESOURCE_LIMIT · CANCELLED`. **A failure is never an empty result** — it is a
distinct status carrying an error.

### Operations

`CALCULATE · AGGREGATE · FILTER · JOIN · DESCRIBE · SUMMARIZE · GROUP · COUNT ·
STATISTICS · CORRELATION · REGRESSION · TRANSFORM · SIMULATE · CUSTOM_PYTHON ·
CUSTOM_SQL`. No arbitrary shell execution.

### Result types

`SCALAR · TABLE · SERIES · DISTRIBUTION · STATISTICS · PLOT · ARTIFACT ·
TEXT_SUMMARY · ERROR`. Results are never flattened to a text string.

---

## Execution profiles

`SAFE · ANALYTICAL · NUMERICAL · SIMULATION` — each bounds time, memory, input,
output, rows, and the allowed operations/modules. Raw executor configuration is
never exposed through MCP. See `ExecutionProfileSpec` in `models.py`.

| Profile | Time | Max rows | Notes |
|---------|------|----------|-------|
| SAFE | 5 s | 10,000 | read/shape/aggregate only |
| ANALYTICAL | 15 s | 200,000 | adds correlation/regression/CUSTOM_SQL |
| NUMERICAL | 30 s | 1,000,000 | adds simulate/CUSTOM_PYTHON |
| SIMULATION | 60 s | 2,000,000 | simulation-oriented |

---

## Resource limits

Every computation is bounded: `max_runtime`, `max_output_bytes`,
`max_input_bytes`, `max_rows`, `max_memory`.

- **`max_input_bytes`** is enforced as an **aggregate per-computation budget**:
  the sum of all resolved dataset sizes must not exceed the profile's
  `max_input_bytes` (a `ResourceLimitError` → `RESOURCE_LIMIT` otherwise).
- **DuckDB** enforcement is **real**: the **whole operation — including dataset
  loading —** runs on a worker thread and is interrupted at the deadline
  (`con.interrupt()` → `ExecutionTimeoutError`), and DuckDB's `memory_limit` is
  set so an operation that exceeds it raises `ResourceLimitError`. `max_rows`
  bounds the returned rows (truncated flag).
- **Python** time/output limits are enforced by the subprocess; the memory
  limit is **best-effort** via `resource` (`RLIMIT_AS`) on POSIX and is
  documented as such — no hard memory limit is claimed where it cannot be set.

---

## Cancellation

Execution is synchronous (there is no background worker to interrupt), so
`cancel()` is only meaningful for a submitted-but-not-yet-executed computation:
it records a `CANCELLED` result. If a terminal result already exists, `cancel`
is a **no-op** and returns the existing result — it never overwrites a
completed/failed/timed-out outcome.

---

## Python execution (gated)

`CUSTOM_PYTHON` (and the `run_python` tool) is **unavailable by default**:
`ComputationService`/`ComputationEngine` accept `enable_python_execution=False`
and raise `UnsupportedOperationError` until hardened isolation (seccomp/
container) exists. See [`python-sandbox.md`](python-sandbox.md).

---

## Dataset inputs

Inputs resolve only through the corpus security layer (root_id/relative_path or
document/dataset id). **Artifact-backed dataset inputs are reserved** — an
`artifact_id` reference raises `DatasetError` rather than silently failing.

---

## Determinism & provenance

Requests may declare `deterministic = true` and a `seed`. Results record:
input datasets (id + content hash), query/code hash, parameters, execution
profile, seed, and software versions. See
[`computation-provenance.md`](computation-provenance.md).

---

## Large results

Small results are returned inline; large results become **artifacts** with a
bounded sample and metadata (`row_count`, `column_count`, `preview`,
`artifact_refs`). A million-row table is never returned through MCP.

---

## Errors

Typed computation errors: `ComputationError`, `ComputationValidationError`,
`ExecutionTimeoutError`, `ResourceLimitError`, `DatasetError`,
`QueryValidationError`, `SandboxError`, `ArtifactError`,
`ComputationNotFoundError`, `ComputationConfigurationError`. They map through
the MCP error boundary without leaking stack traces or sensitive paths.

See [`duckdb.md`](duckdb.md), [`python-sandbox.md`](python-sandbox.md), and
[`../setup/computation.md`](../setup/computation.md).

## Phase 7 — computation stages

The workflow engine's `DESCRIBE_DATASET` / `COMPUTE` stages invoke
`describe_dataset` / `run_analysis` through the runtime; the engine never
constructs DuckDB SQL. See [`workflows.md`](workflows.md).
