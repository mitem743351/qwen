# Tool-Execution Store (Phase 9.4)

The durable, lease-based store backing transactional tool execution.

Module: `python/qwen_research/research/tool_execution.py` (re-exported from
`tool_store.py`).

---

## Interface

`ToolExecutionStore` (protocol):

```text
claim(identity, …)          atomic ownership acquisition
mark_running(identity, lease_id)
heartbeat(identity, lease_id, duration)
complete(identity, lease_id, result)
release(identity, lease_id)
reclaim(identity, …)        explicit stale-claim recovery
mark_unknown(identity, reason)
inspect(identity)           → ToolExecutionRecord | None
is_stale(identity)          → bool
```

`claim()` returns a `ClaimResult` (`CLAIMED` / `ALREADY_COMPLETED` /
`ALREADY_CLAIMED` / `STALE` / `CONFLICT`). Only the active lease owner may
`mark_running` / `heartbeat` / `complete` / `release`.

---

## SQLite implementation

- `PRIMARY KEY (inference_session_id, call_id)` enforces identity uniqueness at
  the database level.
- `claim()` uses `BEGIN IMMEDIATE` — a short transaction — never `SELECT` then
  `INSERT` as two independent operations.
- No database lock is held during tool execution; the lease (with a
  configurable `lease_duration_seconds`, default 120 s) owns the window.
- `heartbeat()` is a conditional `BEGIN IMMEDIATE` update
  (`… WHERE lease_id = ? AND state IN ('CLAIMED','RUNNING')`), verifies
  `rowcount == 1`, and records `heartbeat_at` / `heartbeat_count` on the same
  row. It never resurrects an expired/terminal lease.
- `schema_version` is tracked in `tool_execution_meta` (now `2`, with an
  idempotent v1 → v2 migration adding the heartbeat columns).

### Migration

A legacy Phase 9.3 `tool_executions` cache is migrated into the new
`tool_execution_records` table on `initialize()`, preserving completed results.
Migrated records carry an empty argument hash (unknown) and therefore do not
trigger call-id argument conflicts.

---

## Result storage

Small results are stored inline (serialized `ToolExecutionResult`). Large
results are bounded before entering the model context by the tool loop; artifact
references are the future extension point (no second artifact system is
created).

---

## Lease ownership

`lease_id`, `lease_owner`, `lease_expires_at` are persisted. A stale/incorrect
owner raises `LeaseOwnershipError`; a previous process cannot overwrite a newer
claim. `heartbeat()` refreshes the expiry for long-running work.

See [`tool-execution-reliability.md`](tool-execution-reliability.md).
