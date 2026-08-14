# ADR 0017 — Hybrid escalation contract

- **Status:** Accepted

## Decision

Define an abstract escalation boundary between Studio-native interaction and
gateway-owned workflows: an `EscalationRequest` (`task`,
`requested_reasoning_profile`, `requested_output_profile`,
`required_capabilities`, `reason`, `current_context_reference`,
`session_reference`) and an `EscalationResult` (`status`, `result`, `artifacts`,
`citations`, `state_updates`, `provenance`). Define the contract now; do **not**
implement automatic escalation.

## Reason

Hybrid mode needs a well-defined handoff so that context, session state, and
provenance survive the move from Studio-native into gateway-owned execution and
back. Defining the contract early prevents later ad-hoc coupling, while
deferring automatic escalation avoids premature heuristics (complexity scoring,
auto-routing) that depend on runtime data we do not have yet.

## Alternatives considered

- **Automatic escalation in v1:** premature; the triggers (complexity, depth,
  corpus size) need tuning data that only exists after the system runs.
- **No escalation (modes are mutually exclusive):** simpler, but forfeits the
  key UX of keeping normal interaction in Qwen Studio while deep tasks go
  deep.

## Trade-offs

- A contract to maintain before any implementation uses it.
- Session/context transfer between modes must be specified and tested.

## Reversibility

High. The contract is an interface; it can be expanded, and the decision of
*when* to escalate (explicit user action vs. heuristic) is separable from the
contract itself.
