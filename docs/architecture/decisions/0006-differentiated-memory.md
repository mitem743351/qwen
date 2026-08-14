# ADR 0006 — Differentiated memory stores

- **Status:** Accepted

## Decision

Persist research state in six purpose-specific stores — Session Memory, Project
Memory, Research Memory, Knowledge Base, Unresolved Questions, Decision History
— fronted by a single Memory Manager, with an explicit entity model
(documents, sources, claims, evidence, entities, projects, sessions, decisions,
questions, artifacts). No generic undifferentiated "memory" store.

## Reason

A single memory blob cannot support scoped retrieval, retention policy,
compaction, or auditing. Differentiation lets each store have its own lifetime
and read pattern (session vs. project vs. cross-project vs. append-only), which
is exactly what long-running, resumable research needs.

## Alternatives considered

- **One memory store with a `kind` column:** superficially simpler, but forces
  one retention model and complicates scoped reads and access control.
- **Full knowledge-graph DB in v1:** overkill; relational tables suffice for the
  entity model (graph DB deferred).

## Trade-offs

- Six conceptual stores to manage and migrate.
- Requires the Memory Manager to enforce scoping and compaction.

## Reversibility

High. The stores are repository-backed; boundaries can be merged or split
without changing the Memory Manager's outward interface.
