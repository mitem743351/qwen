# Security Policy

This is the human-facing security posture for the **Qwen Research System**. The
full architectural detail lives in
[`docs/architecture/security.md`](docs/architecture/security.md).

## Posture

The model is assumed to make mistakes — and to be a plausible attack vector via
prompt injection, including injection carried inside corpus documents. Security
is therefore **structural** (permissions, sandboxing, allowlists), never
behavioral (prompt instructions are not a security control).

## Principles

- **Least privilege** — the model never has unrestricted host access by default.
- **Filesystem allowlists** — all filesystem access confined to `corpus/`,
  `data/`, `artifacts/`, and a bounded `workspace/`.
- **Tool permissions** — every MCP tool is `read | analyze | write | execute |
  destructive`; `write` and `destructive` are independently controllable and
  default off; `destructive` requires confirmation.
- **Execution sandboxing** — Python/compute runs isolated: no network by
  default, resource limits, restricted filesystem, no secret access.
- **Local-only network binding** — services bind to `127.0.0.1`/Unix sockets by
  default; remote binding is an explicit opt-in with its own auth.
- **Secret isolation** — secrets never reach logs, artifacts, memory, or model
  context.
- **Audit logging** — tool calls, destructive ops, workflow transitions, and
  verification outcomes are audited.
- **Immutability** — RAW corpus content is never modified.

## Inference ownership and credentials are separate boundaries

MCP permissions and **inference ownership** are distinct. Access to MCP tools
does **not** grant permission to invoke arbitrary model backends, and
Studio-native mode does **not** implicitly gain access to Inference-Runtime
API credentials. Provider secrets live exclusively in the Inference Runtime /
provider adapter and never appear in MCP arguments, tool output, model-visible
context, research state, logs, or artifacts. See
[`docs/architecture/security.md#inference-ownership-as-a-boundary`](docs/architecture/security.md#inference-ownership-as-a-boundary).

## MCP server boundary (Phase 2)

The MCP server is an **external adapter** that defaults to secure operation:

- **Local-only transport** — stdio only; no public network binding.
- **Minimal permissions** — only `read` and `analyze` are enabled by default;
  `write`/`execute`/`destructive` are disabled.
- **Safe error normalization** — internal errors are mapped to safe external
  messages; no stack traces, secrets, API keys, filesystem internals, provider
  credentials, or hidden chain-of-thought are exposed in MCP responses.
- **Session/task isolation** — requests validate that referenced sessions and
  tasks exist; unknown ids map to a safe error.

See [`docs/architecture/mcp-implementation.md`](docs/architecture/mcp-implementation.md).

## Corpus path security and prompt-injection boundary (Phase 3)

- **Allowlisted roots.** Filesystem access is confined to configured corpus
  roots. `../` traversal, absolute paths outside roots, and symlink escapes are
  rejected (symlinks are resolved before containment checks, and refused when
  `follow_symlinks = false`). No unrestricted filesystem tools are exposed.
- **Untrusted documents.** Retrieved document content is **data, never
  instructions**. A document containing "ignore previous instructions" remains
  document content; it cannot alter tool permissions or system behavior. Only
  the model sees retrieved content as evidence.
- **No path leakage.** `PathSecurityError` messages never include the offending
  absolute path; MCP errors are normalized to safe messages.

See [`docs/architecture/retrieval.md`](docs/architecture/retrieval.md) and
[`docs/architecture/corpus.md`](docs/architecture/corpus.md).

## Hidden chain-of-thought

The system **never** stores, transmits, logs, or exposes hidden
chain-of-thought. The persistence layer structurally has no field for it.

## Reporting

This is a local, single-user system under active architecture development. For
issues, open a GitHub issue on the repository; do not include secrets.

## Scope of early phases

Authentication / multi-user RBAC is explicitly out of scope for the initial
implementation phases (single-user local-first). The permission boundary is
designed to be forward-compatible with adding auth later without redesign.
