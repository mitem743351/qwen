# ADR 0015 — Capability negotiation (APPLY / DEGRADE / EMULATE / REJECT)

- **Status:** Accepted
- **Amends:** 0004

## Decision

Providers advertise a `ProviderCapabilities` object (whether they support
reasoning, reasoning budget, max output tokens, temperature, top_p, preserved
thinking, tool calling, structured output, streaming, parallel generation, and
context caching). The translation layer intersects the `InferencePolicy` with
`ProviderCapabilities` and assigns every policy element an explicit outcome —
`APPLY`, `DEGRADE`, `EMULATE`, or `REJECT` — recording every non-`APPLY` outcome
in workflow state and the audit log.

## Reason

A provider must never be *assumed* to support a parameter merely because the
abstract architecture defines it. Explicit negotiation turns "capability" from
an assumption into a discovered fact, and makes degradation observable rather
than silent — which is what keeps `XHIGH` honest across backends.

## Alternatives considered

- **Try/catch on unsupported params:** relies on provider error semantics,
  which are inconsistent and not introspectable up front.
- **Hard-coded per-adapter capability tables:** works but duplicates truth; the
  provider should advertise its own capabilities.
- **Assume a lowest common denominator:** safe but forfeits provider strengths.

## Trade-offs

- Extra negotiation step on every call (negligible cost).
- `EMULATE` can drift from intent; mitigated by an explicit "emulated" marker.

## Reversibility

High. Outcomes are policy handlers behind a negotiation layer; adding or
removing an outcome (or reclassifying one) is a contained change.
