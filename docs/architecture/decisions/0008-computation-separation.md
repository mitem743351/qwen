# ADR 0008 — Deterministic computation separated from model reasoning

- **Status:** Accepted

## Decision

Separate probabilistic/model reasoning from deterministic computation: Python
(sandboxed) for statistics, numerical analysis, simulations, ML, and scientific
workflows; DuckDB for analytical SQL over large tabular data (Parquet/CSV,
aggregations, filtering, joins). The model requests computations and interprets
outputs; it never manually performs large numerical operations.

## Reason

Determinism, auditability, and correctness require a clean split: a model doing
arithmetic/aggregation in prose is error-prone and unreproducible. Routing
deterministic work to real engines yields reproducible, verifiable results that
verification can re-run. The Python/DuckDB split matches each engine's
strength (general compute vs. analytical SQL at scale).

## Alternatives considered

- **Model does everything:** no determinism, no audit trail.
- **Python only (Pandas for analytics):** fine for small data; DuckDB is
  superior and more memory-efficient for large tabular data.
- **DuckDB for everything:** wrong tool for simulations/ML.

## Trade-offs

- Two computation surfaces with separate sandboxing/permission rules.
- Requires schemas for how computations are requested and results returned.

## Reversibility

High. The two engines are behind a single Computation subsystem interface; the
split can be rebalanced without touching callers.
