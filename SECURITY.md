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
