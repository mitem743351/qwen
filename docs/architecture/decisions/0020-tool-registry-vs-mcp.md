# ADR 0020 — Internal Tool Registry vs MCP exposure

- **Status:** Accepted
- **Amends:** 0009

## Decision

Maintain an **internal Tool Registry** (a neutral `Tool` abstraction: name,
description, schema, permission, execution_context, capability) that is
independent of MCP. MCP, CLI, API, and workflow adapters all front this
registry. Only capabilities that have a reason to be exposed to external model
clients are published as MCP tools — MCP is **not** the internal plugin
architecture.

## Reason

Making "every internal function = MCP tool" couples the tool system to one
protocol and forces a small semantic surface (ADR 0009) to carry the weight of
internal extensibility. A neutral registry keeps the permission model and tool
semantics protocol-independent, so CLI/API can reuse them.

## Alternatives considered

- **Tools live only in the MCP server:** simplest, but makes future CLI/API
  clients second-class and conflates exposure with implementation.
- **Two parallel tool systems (MCP + internal):** duplication and drift.

## Trade-offs

- An indirection layer between the registry and each adapter.
- The MCP surface must be curated per tool (exposure is a deliberate decision).

## Reversibility

High. Adapters can be added/removed; the registry is the stable seam.
