# ADR 0001 — Five-layer separation of concerns

- **Status:** Accepted

## Decision

Structure the system as five layers — Qwen Studio → MCP/Gateway → Reasoning +
Orchestration → Knowledge/Computation/Tools → Local Data — with dependencies
pointing strictly downward, and separately distinguish eight concerns (model
capability, inference configuration, reasoning workflow, tool execution,
knowledge retrieval, persistent state, verification, deterministic
computation).

## Reason

The dominant failure mode of agent frameworks is coupling: a retrieval tweak
breaks reasoning, a backend change breaks workflows, a tool change leaks into
prompts. Separating layers (and concerns) makes each change local and makes the
architecture implementable by multiple agents without drift. It also directly
serves the requirement that the system survive a Qwen backend change.

## Alternatives considered

- **Monolith with prompt-only reasoning:** cheapest, but couples everything and
  cannot express XHIGH as real behavior.
- **Microservice per layer:** introduces network boundaries on a single machine
  with no benefit (rejected; see ADR 0011).
- **Actor/graph-based everything:** powerful but premature; over-constrains.

## Trade-offs

- More interfaces and boilerplate up front.
- Requires discipline (the dependency rule is enforced by review, not runtime).

## Reversibility

High. Layers are logical; they can be collapsed into fewer processes later
without changing interfaces, since the contracts are what bind them.
