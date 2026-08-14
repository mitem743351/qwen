# ADR 0012 — Artifacts as first-class, provenance-tracked objects

- **Status:** Accepted

## Decision

Treat every generated output as a first-class `artifact` with identity and
provenance: `artifact_id`, `type`, `path`, `created_at`, `source_session`,
`source_task`, `source_claims`, `source_documents`, `generation_metadata`,
`version`. Artifacts are reproducible and traceable back to the session, task,
claims, and documents that produced them.

## Reason

Generated research outputs (reports, datasets, analyses) must be auditable and
reproducible, not ephemeral chat text. Provenance links the output to the
evidence and reasoning state that produced it, enabling re-derivation,
citation auditing, and trust. Versioning supports iterative refinement.

## Alternatives considered

- **Artifacts as plain files written by tools:** no provenance, no versioning,
  no traceability.
- **Artifacts as database rows only:** fine for metadata, but the bytes need a
  content-addressed home too; hence blob + metadata row.

## Trade-offs

- Every write goes through the Artifact Manager (slightly more ceremony).
- Requires storing `generation_metadata` (prompts/policy versions) for
  reproducibility.

## Reversibility

High. Artifact records are additive; the blob/metadata split can be reorganized
without changing the manager's interface.
