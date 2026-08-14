# Security Architecture

The model is assumed to make mistakes — and to be a plausible attack vector.
Security is designed from that assumption, not added later.

---

## 1. Threat Model

| Actor | Concern |
|-------|---------|
| The model (prompt injection, bad tool calls) | Primary and assumed active |
| Malicious corpus content (documents that are also attack payloads) | Secondary |
| Accidental data loss (wrong destructive call) | Availability/integrity |
| Secret leakage (API keys in outputs/logs) | Confidentiality |

Assumptions:

- The model may request **anything** via tools.
- Corpus content may contain malicious files, formulas, or instructions.
- The operator (single user) is trusted but wants safety rails, not friction.

---

## 2. Principles

```text
least privilege
filesystem allowlists
tool permissions
execution sandboxing
local-only network binding by default
secret isolation
audit logging
destructive-operation confirmation
```

The model is **never** given unrestricted host access by default.

---

## 3. Enforcement Points

### 3.1 Filesystem allowlists

All filesystem access (filesystem tool, Python executor, document pipeline
writes) is confined to explicit allowlisted roots:

```text
corpus/        — read for retrieval/verification; write only via ingest pipeline
data/          — managed storage only
artifacts/     — write target for generated outputs
workspace/     — bounded scratch for computation
```

Anything outside these roots requires explicit, per-session elevation.

### 3.2 Tool permissions

Enforced at the MCP boundary (see [`mcp.md`](mcp.md)): `read`, `analyze`,
`write`, `execute`, `destructive`. `write` and `destructive` are independently
controlled and default off; `destructive` requires confirmation.

### 3.3 Execution sandboxing

`run_analysis` and Python execution run in an **isolated sandbox**:

- no network by default (or a strict egress allowlist),
- resource limits (CPU time, memory, wall-clock),
- filesystem access restricted to `workspace/` and read-only `corpus/`,
- no access to secrets, `.git/config`, or credentials paths.

DuckDB reads are confined to the analytical data directory and are
read-only by default.

### 3.4 Local-only network binding

All services (MCP entrypoint, gateway, any dashboard) bind to `127.0.0.1`
(or Unix domain sockets) by default. Remote binding is an explicit, documented
opt-in with its own auth.

### 3.5 Secret isolation

- Secrets live in environment variables / `.env` (gitignored) and a dedicated
  secret store if needed.
- Secrets are never written to logs, artifacts, memory stores, or model context.
- Model outputs are scanned/redacted before persisting (best-effort, defense
  in depth).

### 3.6 Audit logging

Audit events cover: tool calls (args hashes, result hashes, permissions),
destructive operations, workflow stage transitions, verification outcomes,
and configuration changes. Logs never contain chain-of-thought or secrets.

### 3.7 Inference ownership as a boundary

MCP permissions and **inference ownership** are **separate** security
boundaries:

- A client granted MCP tool access does **not** automatically gain permission
  to invoke arbitrary model backends.
- `STUDIO_NATIVE` mode must **not** implicitly gain access to gateway-owned API
  credentials.
- Credentials are isolated from tool payloads and model-visible context; the
  inference adapter's credentials never cross the MCP boundary.

The Mode Selector enforces this: in `STUDIO_NATIVE` the Inference Adapter is
not exercised, so there is no path for tool calls to reach model backends.

---

## 4. What the Model Can Never Do (by default)

```text
- read or write outside allowlisted roots
- access the network beyond localhost
- read secret material
- delete/overwrite RAW corpus content
- escalate its own permissions
- call a tool whose permission class is disabled for the session
```

---

## 5. Failure Modes & Mitigations

| Risk | Mitigation |
|------|------------|
| Prompt injection in a document | Corpus content treated as data, never as instructions; tool calls gated by permissions regardless of origin |
| Model asks for `destructive` op | Confirmation + independent enablement + audit |
| Code execution escapes sandbox | Defense in depth: OS-level sandbox (Rust-process boundary), no-network default, resource limits |
| Secrets in model output | Redaction on the persist path |
| Corpus tampering | RAW immutability + content hashing + index versioning |
| MCP grant ⇒ backend access | Separate boundaries: tool permissions ≠ inference ownership |
| Credential bleed into Studio-native tools | Credentials isolated; never in tool payloads or model context |

---

## 6. Decision Record

- [0013 — Least-privilege security model](decisions/0013-least-privilege.md)
