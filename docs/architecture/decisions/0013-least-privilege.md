# ADR 0013 — Least-privilege security model

- **Status:** Accepted

## Decision

Assume the model makes mistakes and enforce: least privilege, filesystem
allowlists, class-based tool permissions, execution sandboxing, local-only
network binding by default, secret isolation, audit logging, and
destructive-operation confirmation. The model never has unrestricted host
access by default. RAW corpus content is immutable.

## Reason

The model is both fallible and a plausible injection vector (corpus content can
carry instructions). Defense must be structural (permissions, sandboxing,
allowlists) rather than behavioral (prompt instructions), because prompts are
not a reliable security control.

## Alternatives considered

- **Trust the model + prompts:** fragile; a single bad tool call or injected
  document defeats it.
- **Full multi-user auth/RBAC in v1:** unnecessary for single-user local-first;
  deferred (auth is explicitly out of scope for early phases).

## Trade-offs

- Friction: some legitimate operations require enablement/confirmation.
- Sandboxing adds runtime cost and complexity.

## Reversibility

Partial. Tightening later is easy; the boundary design is forward-compatible
with adding auth/RBAC. Loosening later would be a policy change, not a redesign.
