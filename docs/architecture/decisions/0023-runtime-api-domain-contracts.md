# ADR 0023 — Runtime API and domain contracts

- **Status:** Accepted
- **Amends:** 0005 (implicitly, re: transport neutrality)

## Decision

Define a transport-neutral **Research Runtime API**
(`execute_task`, `continue_task`, `inspect_task`, `retrieve_context`,
`verify_claim`, `run_workflow`, `get_state`, `save_artifact`) and a set of
internal **domain objects** (`Task`, `Session`, `ResearchPlan`,
`ResearchState`, `Evidence`, `Claim`, `Source`, `Artifact`, `Workflow`,
`ReasoningProfile`, `ReasoningBudget`, `InferencePolicy`, `InferenceResult`,
`VerificationResult`, `EscalationRequest`, `EscalationResult`) that are
independent of any wire schema. The MCP schema is adapted to/from these; it is
not the internal domain model.

## Reason

When the wire schema is the domain model, protocol changes ripple through the
entire system and non-MCP clients are forced to speak MCP. A transport-neutral
API + domain model keeps business logic stable across MCP, HTTP, stdio,
in-process calls, and future RPC.

## Alternatives considered

- **Use MCP types as the domain model:** fast, but couples everything to one
  protocol and makes a CLI/API second-class.
- **Adapters that translate per call site:** inconsistent and error-prone.

## Trade-offs

- Mapping code between transport schemas and domain objects.
- Domain objects must be versioned and documented independently.

## Reversibility

High. This is an additive layer of indirection; it can be thinned where a
transport and the domain genuinely coincide, without changing callers.
