# ADR 0019 — Research Runtime vs Inference Runtime separation

- **Status:** Accepted
- **Amends:** 0004, 0016

## Decision

Separate the **Research Runtime** (provider-independent orchestration and
research policy) from the **Inference Runtime** (provider-facing model
invocation: provider selection, capability discovery, policy translation,
parameter validation, request construction, streaming, retries, response
normalization). The Inference Runtime never calls upward into the Research
Runtime.

## Reason

Reasoning workflow policy and provider mechanics fail and change for different
reasons. Coupling them makes workflows provider-specific and makes providers
hard to swap. A dedicated Inference Runtime keeps every provider detail behind
one seam (extending ADR 0004) while the Research Runtime stays provider-neutral
— which is exactly what the "survive a Qwen backend change" requirement demands.

## Alternatives considered

- **Inference as a set of methods on the runtime:** the Phase 0 arrangement;
  works but allows provider specifics to leak into workflow code.
- **Inference as a separate service:** rejected — network boundary on one
  machine with no benefit (see ADR 0021).

## Trade-offs

- An explicit `InferenceRequest`/`InferenceResult` contract to maintain.
- Slightly more indirection per model call (negligible).

## Reversibility

High. The Inference Runtime is an in-process module; it can be inlined back
into the Research Runtime without changing callers, though that would re-couple
the concerns.
