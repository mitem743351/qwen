# ADR 0014 — Inference ownership and operating modes

- **Status:** Accepted
- **Amends:** 0003, 0004, 0009

## Decision

Model inference ownership as a first-class architectural concept with three
explicit operating modes — `STUDIO_NATIVE`, `GATEWAY_INFERENCE`, `HYBRID` —
each described by a `CapabilityMode` object, and adopt the rule that MCP
extends a model with **capabilities** without granting the MCP server control
over the host client's **inference** parameters or reasoning loop.

## Reason

The Phase 0 architecture correctly defined reasoning, MCP, retrieval, memory,
verification, and provider abstractions, but did not state *who owns the model
inference loop*. This omission allowed a misleading reading — "Qwen Studio →
gateway → inference" — that implies an MCP server controls Qwen Studio's hidden
reasoning budget, temperature, `top_p`, or generation limits, which it does
not. Making ownership explicit prevents the system from claiming capabilities
it does not have, and reserves true API-grade orchestration for the modes that
can actually deliver it.

## Alternatives considered

- **Single implicit "gateway controls everything" model:** simplest, but factually
  wrong for Studio-hosted inference and encourages over-claiming.
- **No mode distinction (document caveats inline):** too easy to regress into
  ambiguous claims; a first-class `CapabilityMode` + capability matrix is
  reviewable and testable.

## Trade-offs

- Adds a mode dimension to configuration, testing, and documentation.
- Requires every capability claim to be qualified by mode (more verbose).

## Reversibility

High. Modes are additive configuration concepts; a mode can be deprecated or a
new one added without redesigning the underlying subsystems.
