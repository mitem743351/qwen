# ADR 0007 — Verification as a first-class, independently callable subsystem

- **Status:** Accepted

## Decision

Make verification a first-class subsystem (claim verification, evidence
verification, source quality, contradiction detection, counterexample search,
citation auditing, calculation validation, cross-document consistency),
callable both automatically within deep workflows and explicitly via MCP.

## Reason

Trust in generated research is a core value, and the model is assumed capable
of error. Verification must be able to run even when the workflow doesn't
request it (e.g. a user calls `verify_claim` directly), and its outcomes must
be able to redirect the workflow (loop back to retrieval/reasoning). Coupling
verification to a specific workflow stage would make it unreusable and hard to
test.

## Alternatives considered

- **Verification as a prompting step:** cheap but unmeasurable and can't do
  deterministic checks (citation/calculation).
- **Verification inside retrieval:** conflates "relevant" with "true"; wrong.

## Trade-offs

- A distinct component with its own interface and state model.
- Additional latency in deep profiles (mitigated by `verification_passes` dial).

## Reversibility

High. Verifiers are registered checks behind one engine; individual checks can
be added/removed without touching the workflow.
