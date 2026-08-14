# ADR 0009 — Small semantic MCP surface with class-based permissions

- **Status:** Accepted

## Decision

Expose a small set of high-value semantic tools (`search_corpus`,
`retrieve_evidence`, `read_source`, `get_research_state`, `query_database`,
`run_analysis`, `verify_claim`, `find_contradictions`, `save_artifact`,
`get_project_context`) behind a permission boundary with classes
`read | analyze | write | execute | destructive`, where `write` and
`destructive` are independently controllable. Never expose a universal
`execute_anything`.

## Reason

A small semantic surface keeps the model's action space comprehensible,
auditable, and permissionable. A universal tool would make least privilege
impossible to enforce and every tool call unreviewable. Class-based permissions
let "read-only research" and "can write artifacts" be configured independently.

## Alternatives considered

- **Expose all internal functions:** maximal flexibility, but leaks internals,
  causes drift, and breaks the permission model.
- **A single universal tool:** rejected outright (violates least privilege).
- **Per-tool boolean flags only:** works but doesn't capture the
  read/analyze/write/execute/destructive escalation cleanly.

## Trade-offs

- The surface is deliberately limited; new capabilities require an explicit new
  tool + permission class rather than ad-hoc calls.

## Reversibility

High. Tools are registered additions; the registry and boundary can be extended
without redesign. The MCP SDK itself sits behind a façade (swap-able).
