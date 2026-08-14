# ADR 0010 — Dedicated Context Engine

- **Status:** Accepted

## Decision

Create a dedicated Context Engine that decides what enters model context, what
stays out, what is summarized vs. verbatim, what is deduplicated, how evidence
is prioritized, how budget is allocated across task components, how long
sessions are compacted, and how continuation state is restored. Context
management is never simple string concatenation.

## Reason

Context is the scarcest and most error-prone resource in agent systems. Ad-hoc
prompt assembly spreads budget logic everywhere, silently drops disconfirming
evidence, and breaks resumability. Centralizing it makes budgeting,
prioritization, and compaction testable and consistent.

## Alternatives considered

- **Concatenate everything until limit:** trivial but drops evidence and loses
  structure.
- **Context logic inside the workflow engine:** possible, but mixes two
  concerns (what to do vs. what the model sees) and blocks independent tuning.

## Trade-offs

- Another component with a nontrivial responsibility.
- Requires a notion of "context item" (typed records with priority/provenance).

## Reversibility

Moderate. The engine's interface is stable; its internal strategy can evolve.
Collapsing it back into the workflow engine is possible but would re-couple the
concerns.
