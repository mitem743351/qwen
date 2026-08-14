# MCP Implementation (Phase 2)

> **Status:** Phase 2 foundation implemented. This documents what **exists** in
> `python/qwen_research/mcp/`, and distinguishes it from future MCP capability.

---

## What Phase 2 delivers

A **real, testable external adapter**: Qwen Studio (or another MCP client)
connects over stdio to an MCP server that exposes a minimal set of Research
Runtime operations. The MCP layer is an **adapter**, not the research system.

```text
Qwen Studio ── MCP (stdio) ──▶ MCP Server ──▶ Research Runtime ──▶ Domain
```

---

## Library decision

- **Dependency:** [`mcp`](https://pypi.org/project/mcp/) `>=1.9,<3` — the
  official Model Context Protocol Python SDK (reference implementation),
  maintained by the MCP project.
- **Why:** it is the maintained official reference implementation; it supports
  stdio transport, tool registration, input-schema inference, and local-server
  operation, and it is the surface Qwen Studio/Desktop expects.
- **Boundary:** the SDK is imported **only** inside `python/qwen_research/mcp/`.
  The Research Runtime and Domain layers have no MCP dependency.
- **Transport:** stdio (the local-first default for Qwen Studio). The transport
  is behind a `MCPTransport` abstraction (`transport.py`) so Streamable HTTP /
  SSE can be added later without touching tools or the runtime.

---

## Server architecture

```text
MCPServerApp (server.py)          — lifecycle, tool registration, diagnostics
   ├── SDK MCPServer              — protocol engine (the `mcp` SDK)
   ├── SchemaAdapter (adapters.py)— MCP args/results ↔ domain objects
   ├── ToolPermissionPolicy       — permission model + enforcement
   ├── map_error (errors.py)      — internal errors → safe external errors
   └── MCPTransport (transport.py)— stdio now; SSE/HTTP later
```

Tool handlers are thin: validate → translate → invoke Research Runtime →
translate → return. No reasoning, business rules, database queries, Qwen calls,
or retrieval logic lives in the MCP layer.

---

## Tools (Phase 2 minimal set)

| Tool | Permission | Research Runtime operation |
|------|-----------|---------------------------|
| `get_session` | READ | `get_session` |
| `create_session` | ANALYZE | `create_session` |
| `execute_task` | ANALYZE | `execute_task` |
| `continue_task` | ANALYZE | `continue_task` |
| `get_task_state` | READ | `inspect_task` |
| `get_research_state` | READ | `get_state` |

Input schemas live in `schemas.py` (JSON-Schema dicts, the semantic authority);
the SDK infers compatible wire schemas from the handler signatures.
`WRITE`/`EXECUTE`/`DESTRUCTIVE` are **not** granted by any Phase 2 tool.

**Not exposed yet** (their underlying implementations do not exist):
`search_corpus`, `retrieve_evidence`, `verify_claim`, `run_analysis`.

---

## Permission model

`MCPPermission` (`READ`/`ANALYZE`/`WRITE`/`EXECUTE`/`DESTRUCTIVE`) with a
`ToolPermissionPolicy`. `guarded_call()` enforces the policy per invocation and
maps any internal error through `map_error()`. Permissions default to
secure: only `read` and `analyze` enabled.

---

## Error normalization

`errors.py` maps internal domain errors to safe external errors — never stack
traces, secrets, API keys, filesystem internals, credentials, or hidden
chain-of-thought:

| Internal error | External result |
|----------------|-----------------|
| `ValidationError` / `InvalidTransitionError` | `INVALID_PARAMS` — "invalid arguments" |
| `PermissionError` | `INVALID_PARAMS` — "permission denied" |
| `UnsupportedOperationError` | `INTERNAL_ERROR` — "capability unavailable" |
| other `DomainError` | `INTERNAL_ERROR` — safe message |

---

## Session/task isolation

The server distinguishes caller, `session_id`, and `task_id`. It does not
assume one MCP connection = one session. `execute_task` validates that a
provided session exists; `get_session`/`get_task_state`/`get_research_state`
validate existence (unknown ids map to a safe error). Caller identity is
implicit for the single local user (stdio); a future remote transport would
add authentication.

---

## Lifecycle & diagnostics

`MCPServerApp` supports initialize (construction) → `serve()` (blocking) →
`shutdown()`. The stdio server exits cleanly when the client closes stdin (no
orphan child processes). `diagnostics()` returns local status, version,
transport, and the registered tool list — no sensitive data.

---

## Testing

- **Unit** (`tests/mcp/`): schemas, adapters (MCP↔domain), permissions, error
  mapping, server construction/lifecycle, guarded dispatch.
- **Integration** (`test_integration.py`): a real stdio subprocess round-trip
  using the official MCP client — discovery, all six tools, structured results,
  error normalization, and shutdown. No Qwen or network required.

---

## Explicitly NOT implemented (future MCP capabilities)

- `search_corpus` / `retrieve_evidence` / `verify_claim` / `run_analysis` tools
- MCP resources (project context, documents, artifacts) — reserved until their
  semantics exist
- Streamable HTTP / SSE transports
- Remote transport / authentication
- Qwen API, retrieval, real persistence, document parsing, computation engine

See [`mcp.md`](mcp.md) for the architecture contract and
[`../setup/mcp.md`](../setup/mcp.md) for running instructions.
