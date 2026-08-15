# DuckDB Analytics Engine

DuckDB is the analytical engine for Phase 6. It is **always** behind the
`AnalyticsEngine` boundary — the Research Runtime and MCP never see a raw
DuckDB connection, and SQL lives only inside the computation layer.

Module: `python/qwen_research/computation/analytics.py`.

---

## Boundary

```text
Research Runtime
    ↓ (typed operations, no SQL)
AnalyticsEngine (DuckDBBackend)
    ├── describe_dataset · run_query · aggregate · group · filter · join · count
    ↓
DuckDB (in-memory, external access disabled for user SQL)
```

Each call opens a fresh in-memory database, loads the approved datasets into
safely-named tables, disables external access, and runs the (validated) query.
No connection or raw path escapes the backend.

---

## Supported formats

`CSV` (`read_csv_auto`), `JSON` (`read_json_auto`), `Parquet`
(`read_parquet`), and `SQLite` tables (read via the stdlib `sqlite3` driver
with declared column types mapped to DuckDB types). Dataset paths are resolved
through the corpus security layer first — the backend only ever sees resolved,
contained paths.

---

## SQL safety

- User SQL runs with `enable_external_access = false`, which blocks `ATTACH`,
  `COPY`, `INSTALL`/`LOAD` extensions, and file-reading functions
  (`read_csv`/`read_parquet`/`read_json`/…).
- Statement validation (`validate_sql`) rejects forbidden constructs and
  **multiple statements** before they reach DuckDB.
- Identifier validation (`validate_identifier`) enforces a strict
  `[A-Za-z_][A-Za-z0-9_]*` pattern for any column/grouping name.
- Values are parameterized (`:name` → positional `?`); identifiers are never
  interpolated.

### Explicitly blocked

```text
COPY TO / COPY FROM arbitrary filesystem locations
ATTACH arbitrary databases
read arbitrary filesystem paths (read_csv_auto, read_parquet, glob, …)
INSTALL / LOAD extensions
PRAGMA (in user SQL)
```

---

## Execution enforcement

- **Timeout** — DuckDB has no native statement timeout; the **whole operation
  (dataset loading + query/profile)** runs on a worker thread and
  `con.interrupt()` fires at the deadline, raising `ExecutionTimeoutError`.
  This is a real bound, not a best-effort one.
- **Memory** — `SET memory_limit` is applied on the connection; an operation
  (including dataset load) that exceeds it raises `ResourceLimitError`
  (`OutOfMemoryException` is translated, never leaked raw).
- **Result size** — `max_rows` bounds returned rows (with a `truncated` flag)
  and `max_output_bytes` aborts oversized results.

These are exercised by adversarial workload tests (cartesian products, large
distinct hash sets, oversized outputs, slow dataset loads).

---

## Statistics & regression

Numeric columns are extracted and passed to the pure-stdlib
[`descriptive`](computation.md) statistics module; correlation is labelled
correlation (never causality), and regression is descriptive least squares.
DuckDB handles the large tabular operations; the numerical baseline is
deterministic and dependency-light.
