# ADR 0002 — Polyglot boundaries

- **Status:** Accepted

## Decision

Use a deliberate polyglot stack with strict ownership: Python (primary
AI/reasoning), Rust (systems/performance, bound via PyO3 FFI), TypeScript
(optional dashboard only), SQL (SQLite/PostgreSQL for system-of-record,
DuckDB for analytics), Shell (ops only). No network boundaries between Python
and Rust on a single machine.

## Reason

Each domain has a best-fit language. Python's ecosystem dominates the
model/document/ML surface; Rust's memory safety and performance dominate
filesystem/indexing/sandbox work. Forcing one language everywhere produces
either slow Python or slow-to-write Rust. The polyglot approach assigns each
concern to its natural home while FFI keeps the boundary cheap.

## Alternatives considered

- **Python-only:** simplest; fails on hot filesystem/indexing paths and lacks
  the safety guarantees desired for sandboxing.
- **Rust-only:** excellent performance; far slower iteration and a thin
  ML/document ecosystem — wrong for the reasoning layer.
- **Separate services per language:** rejected; adds network tax on one machine
  (see ADR 0011).

## Trade-offs

- Two toolchains to manage.
- FFI boundary is a small, permanent abstraction cost.

## Reversibility

High per-capability: each Rust module is reached through a Python protocol, so
a module can be rewritten in Python (or vice versa) without touching callers.
The "profile first" rule makes Rust adoption incremental and reversible.
