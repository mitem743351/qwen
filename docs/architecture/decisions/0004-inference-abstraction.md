# ADR 0004 — Provider-independent inference abstraction

- **Status:** Accepted
- **Amended by:** 0014, 0015

## Decision

All model access goes through a provider-independent `InferenceProvider`
interface (`capabilities`, `model_info`, `generate`, `stream`,
`structured_output`, `tool_call`), with adapters for Qwen API, Qwen-compatible
endpoints, future local Qwen, and future alternative providers. Provider
parameters live only inside adapters; a translation layer maps
`ReasoningProfile → InferencePolicy → capability negotiation →
provider-specific parameters` (see ADR 0015).

## Reason

The explicit requirement is to remain useful if the Qwen backend changes. A
single seam that isolates all provider-specific behavior makes a backend swap a
configuration change. `capabilities()` additionally lets the adapter degrade
gracefully and *record* when a backend cannot honor part of a policy.

## Alternatives considered

- **Direct Qwen SDK calls throughout:** fastest to build, but provider-locked
  and scatters params across the codebase.
- **Full provider abstraction over-engineered (multi-region, routing, caching):**
  unnecessary for local-first single-user; deferred.

## Trade-offs

- The interface is the lowest common denominator; provider-specific extras must
  be expressed via `capabilities()` rather than surfaced directly.
- Slight indirection cost on every call (negligible).

## Reversibility

High. Adapters are swappable; the protocol can grow additively. Reverting to
direct calls would be a mechanical change, not a redesign.
