# ADR 0016 — Gateway as capability/orchestration boundary (conditional inference ownership)

- **Status:** Accepted
- **Amends:** 0011

## Decision

Define the Local Research Gateway as *the local capability and orchestration
boundary that exposes research infrastructure to clients and, in
gateway-owned inference mode, additionally owns model orchestration.*
Inference ownership is conditional on operating mode. Replace ambiguous usage
of "gateway" with four control planes: model, agent, knowledge, and interface.

## Reason

The phrase "the gateway controls Qwen" conflates three different things: who
serves capabilities, who orchestrates a workflow, and who owns the inference
loop. In `STUDIO_NATIVE` mode the gateway provides capabilities and (optionally)
tool-assisted workflow influence but does **not** own inference. Naming the four
planes removes the ambiguity that caused the original over-claim.

## Alternatives considered

- **Rename the gateway:** cosmetic; the problem is the *scope*, not the name.
- **Two separate components (capability server vs. orchestrator):** clearer but
  forces a boundary that is unnecessary on a single machine; a single component
  with conditional ownership is simpler and reversible.

## Trade-offs

- One component with conditional behavior is slightly less "pure" than two.
- Documentation must always state which plane/ownership a statement refers to.

## Reversibility

Moderate. Splitting the gateway into separate capability/orchestration
components later is a contained change because their responsibilities are
already enumerated distinctly.
