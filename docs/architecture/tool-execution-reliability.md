# Tool-Execution Reliability (Phase 9.4)

Transactional execution around model-requested tool calls.

Module: `python/qwen_research/research/tool_execution.py`.

---

## Guarantee (precise)

The system does **not** claim universal exactly-once execution. The accurate
guarantee is:

> **A live execution remains claim-owned while its lease is renewed. An
> execution whose lease expires without successful renewal becomes recoverable
> according to its tool execution semantics and recovery policy. Durable
> terminal results are replayable; ambiguous side-effecting executions are
> represented as UNKNOWN rather than silently retried.**

The actual guarantee is: atomic claim + exclusive lease ownership +
heartbeat-based liveness + durable completion + explicit `UNKNOWN` crash state +
tool-specific recovery policy.

---

## Execution identity

`ToolExecutionIdentity(inference_session_id, call_id)` is the canonical,
immutable identity (enforced as the SQLite primary key). Tool name, argument
hash, timestamp, etc. are diagnostic metadata, never the primary key.

---

## State machine

`ToolExecutionState`: `PENDING`, `CLAIMED`, `RUNNING`, `SUCCEEDED`, `FAILED`,
`DENIED`, `INVALID_ARGUMENTS`, `TIMEOUT`, `RESOURCE_LIMIT`, `CANCELLED`,
`UNKNOWN`, `ABANDONED`.

- `PENDING` — record exists, no active lease (fresh or released).
- `CLAIMED` — an owner holds the lease; no second owner may execute.
- `RUNNING` — the tool has actually started.
- terminal states (`SUCCEEDED` … `CANCELLED`) — a durable outcome exists.
- `UNKNOWN` — the system cannot determine whether the external operation
  completed. **Never silently retried for side-effecting tools.**
- `ABANDONED` — an execution claim known to be stale (not auto-derived from
  `UNKNOWN`).

---

## Claim / lease semantics

`claim()` is atomic (`BEGIN IMMEDIATE` + `PRIMARY KEY`): two concurrent callers
can never both receive ownership. Outcomes:

- `CLAIMED` — new ownership with a fresh `lease_id` / `lease_owner` /
  `lease_expires_at`.
- `ALREADY_COMPLETED` — a terminal result is replayed (no execution).
- `ALREADY_CLAIMED` — another owner holds an unexpired lease.
- `STALE` — an active lease has expired.
- `CONFLICT` — the call id was reused with a different tool / arguments / scope.

Only the holder of the active `lease_id` may `mark_running`, `heartbeat`,
`complete`, or `release`; a wrong/expired owner raises `LeaseOwnershipError`.
The SQLite transaction is **short** (claim, then commit); no database lock is
held during actual tool execution — the lease provides ownership.

## Lease liveness & heartbeats (Phase 9.5)

A live execution renews its lease via a **heartbeat**: a local daemon thread
(`LeaseHeartbeat`) extends `lease_expires_at = now + lease_duration` at a
configurable `heartbeat_interval` (default `lease/4`; recommended ≤ `lease/3`).
The key invariant:

> An active execution with a valid heartbeat remains owned by its executor and
> does not become reclaimable merely because the original lease duration
> elapsed.

`heartbeat()` is a conditional, short SQLite transaction: it updates the row
only where `lease_id` matches and `state IN ('CLAIMED','RUNNING')`, verifies
`rowcount == 1`, and otherwise raises `LeaseOwnershipError` — a lost/expired/
terminal lease is never resurrected. Each heartbeat also records `heartbeat_at`
and increments `heartbeat_count` on the same execution row (no write
amplification beyond the record update).

- Scheduling uses a **monotonic** clock; persisted timestamps remain wall-clock
  UTC.
- Heartbeat failures retry a bounded number of times (tolerating SQLite
  contention); after that the lease is `LOST` and the owning transaction stops
  assuming ownership.
- On `LOST`: a read-only/idempotent execution may still complete; a
  side-effecting/unknown execution is recorded as `UNKNOWN` (never falsely
  committed as owned).
- The heartbeat is stopped before `complete()`; a heartbeat firing after a
  terminal result is a no-op (terminal states reject it).

The lease timeout and the tool timeout are **distinct**: the lease says "how
long ownership stays valid without renewal", the tool timeout says "stop/limit
the operation". A tool may run longer than the lease as long as heartbeats keep
it alive.

---

## Recovery by tool semantics

`ToolExecutionSemantics`: `READ_ONLY`, `IDEMPOTENT`, `SIDE_EFFECTING`,
`DESTRUCTIVE`, `UNKNOWN` (defaults derived from permission classes; a tool may
declare `execution_semantics` explicitly).

- `READ_ONLY` / `IDEMPOTENT` — a stale claim may be safely reclaimed
  (`RECLAIM_STALE_IF_SAFE`, the default).
- `SIDE_EFFECTING` / `DESTRUCTIVE` / `UNKNOWN` — a stale claim is recorded as
  `UNKNOWN` and requires explicit recovery; it is never auto-retried.

`ToolRecoveryPolicy` is explicit (`RECLAIM_STALE_IF_SAFE` /
`FAIL_ON_UNKNOWN`); it is never inferred from exception handling.

---

## Replay policy

Terminal outcomes replay deterministically: `SUCCEEDED`, `DENIED`,
`INVALID_ARGUMENTS`, `CANCELLED`. `UNKNOWN` is **never** replayed as success.

## Call-ID conflict

A call id reused with a different `tool_name`, `arguments_hash`, or `project_id`
is `CONFLICT` (no execution). The arguments hash is a deterministic SHA-256 of
canonical JSON (key order normalized); `repr()` is never hashed.

---

## Persistence

`SqliteToolExecutionStore` (and an in-memory variant) stores only safe
metadata: identity, tool name, argument hash, project/session/task/run,
state, semantics, permission, lease fields, attempt, timestamps, result,
provenance. No credentials, private prompts, hidden reasoning, or large raw
tool payloads are persisted.

See [`tool-store.md`](tool-store.md) and
[`../setup/tool-execution.md`](../setup/tool-execution.md).
