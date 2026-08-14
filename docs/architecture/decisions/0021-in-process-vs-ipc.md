# ADR 0021 — In-process vs IPC boundary policy

- **Status:** Accepted
- **Refines:** 0002, 0011

## Decision

Implement the three runtimes as **logical boundaries first**, realized on a
single machine with the cheapest boundary that provides the required isolation:

```text
same process/library  >  FFI  >  local IPC  >  network
```

The default is **in-process modules**; FFI for Rust hot paths; local IPC only
where isolation (e.g. sandboxing) requires it; network only as an explicit,
opt-in future choice. `apps/mcp-server`, `apps/research-runtime`,
`apps/inference-runtime` do **not** imply three mandatory network daemons.

## Reason

The runtime boundaries exist to prevent architectural coupling, not to force
process boundaries. Network/IPC between runtimes on one machine adds latency,
serialization, failure modes, and ops burden with no single-user payoff
(extending ADR 0011). The polyglot FFI rule (ADR 0002) already prefers FFI over
network for Python↔Rust.

## Alternatives considered

- **Three microservices:** explicitly rejected; unnecessary deployment
  complexity for local-first single-user.
- **One undifferentiated monolith:** rejected; loses the boundaries this phase
  establishes.

## Trade-offs

- In-process runtimes share fate (a crash takes all down) — mitigated by the
  logical failure-isolation model (ADR 0022).
- Promoting a runtime to a separate process later is a contained change.

## Reversibility

High. Deployment topology is orthogonal to the logical boundaries; any runtime
can be promoted to IPC/network later without redesign.
