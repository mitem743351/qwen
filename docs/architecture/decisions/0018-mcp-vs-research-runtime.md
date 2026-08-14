# ADR 0018 — MCP Server vs Research Runtime separation

- **Status:** Accepted
- **Amends:** 0016

## Decision

Split the "gateway" into distinct logical runtimes, beginning with a hard
boundary between the **MCP Server** (capability exposure, protocol, validation,
permissions, transport) and the **Research Runtime** (planning, reasoning
policy, retrieval, memory, verification, workflows, persistence). The MCP
Server is an adapter onto the Research Runtime API and owns none of the
research logic.

## Reason

When MCP and the research engine are one component, the protocol contaminates
the domain model, the system cannot be used except through MCP, and every
internal function tends to leak into the tool surface. Separating them makes
the Research Runtime usable by CLI/API/dashboard without pretending to be an
MCP client, and makes MCP replaceable.

## Alternatives considered

- **Keep a single "gateway" that serves MCP:** simplest, but reintroduces the
  monolith this phase exists to prevent.
- **Make MCP a thin SDK binding inside the runtime:** better than a monolith
  but still couples protocol to the domain.

## Trade-offs

- One more boundary to design and test.
- Requires the domain objects to be transport-neutral (see ADR 0023).

## Reversibility

High. The MCP Server is an adapter; it can be re-merged with the runtime (or
re-split) without changing the Research Runtime API.
