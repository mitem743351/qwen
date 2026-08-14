# ADR 0022 — Runtime failure isolation

- **Status:** Accepted

## Decision

Define independent failure behavior for each runtime and subsystem, so a
failure degrades a bounded capability rather than the whole system:

| Failure | Behavior |
|---------|----------|
| MCP Server fails | Studio loses external tools; normal conversation continues |
| Research Runtime fails | MCP reachable; research operations fail with structured error |
| Inference Runtime fails | research tools usable; gateway-owned reasoning stops |
| Retrieval fails | report insufficient evidence; never fabricate |
| Provider fails | retry / switch provider / explicit failure per policy |

## Reason

A local research system must fail honestly. When components share fate without
a defined failure model, an outage in one place manifests as silent wrong
answers (e.g. a failed retrieval silently producing unsupported claims). Named
failure behaviors make degradation explicit, auditable, and testable.

## Alternatives considered

- **Fail-fast everywhere:** clear but unnecessarily brittle for single-user use
  where partial capability is valuable.
- **Silent degradation:** unacceptable — hides evidence gaps and provider
  outages.

## Trade-offs

- Each boundary needs an error contract and test coverage.
- Some complexity in handling "degraded but alive" states.

## Reversibility

High. Failure behaviors are policy per boundary; tightening or loosening them
is a configuration/policy change, not a redesign.
