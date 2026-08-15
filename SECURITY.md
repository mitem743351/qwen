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

## Memory isolation and untrusted content (Phase 4)

- **Project/session isolation.** Memory is scoped by project (and session)
  at repository/query boundaries; project A's memory never appears in project B
  unless explicitly shared. This is enforced structurally, never by prompts.
- **Untrusted content.** Retrieved documents and stored memory are **data, not
  instructions** — they never carry control-plane meaning (system/developer
  instructions, tool permissions, or security policy). Control-plane config is
  kept separate from knowledge-plane content.
- **Write permission.** `save_research_memory` requires the `WRITE` permission
  class (disabled by default); memory reads are `READ`.

See [`docs/architecture/memory.md`](docs/architecture/memory.md).

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

## Verification integrity (Phase 5)

- **Untrusted content.** Claims, evidence excerpts, source metadata, and stored
  memory are **data, never instructions**. Verification reads corpus text and
  metadata as untrusted input; a malicious document or claim can never modify
  permissions, verification rules, prompts, or database queries. All SQL is
  parameterized; retrieved/stored text is never interpolated into control
  plane.
- **Atomic writes.** `create_claim` / `link_claim_evidence` validate referenced
  claims and evidence **before** committing; an unresolved reference raises a
  typed error and persists nothing.
- **Bounded claims.** Verification statuses are scoped to the corpus
  (`VERIFIED_WITHIN_CORPUS`) — the system never asserts absolute truth, so a
  verified claim cannot be silently escalated into a security-relevant
  fact. `UNREVIEWED` claims are never auto-promoted.
- **No model/network.** The Phase 5 verification engine is deterministic and
  offline: no model calls, no web scraping, no LLM judge.

## Computation sandbox & injection (Phase 6)

Model-generated SQL and Python are **untrusted executable input** — never
assumed safe because "the model wrote it".

- **SQL.** DuckDB queries run with `enable_external_access = false`; statement
  validation rejects `ATTACH`/`COPY`/`INSTALL`/`LOAD`/`PRAGMA` and file-reading
  functions; values are parameterized; identifiers are validated against schema
  metadata. SQL cannot read or write arbitrary filesystem locations. Queries
  are also bounded by a real timeout (worker-thread interrupt) and DuckDB's
  `memory_limit` (`ResourceLimitError`).
- **Python.** Executes in a separate OS subprocess with a restricted builtins
  namespace (no `__import__`, `open`, `eval`, `subprocess`, `socket`), enforced
  time/output limits, and best-effort memory limits. `run_python` /
  `CUSTOM_PYTHON` is **unavailable to model-driven execution** — it raises
  `UnsupportedOperationError` unless the service is explicitly constructed with
  `enable_python_execution=True` (the shipped server never sets this). It is
  additionally `EXECUTE`-gated and disabled by default.
- **Datasets.** Inputs resolve only through the corpus security layer; arbitrary
  OS paths are never accepted from MCP. Artifact-backed dataset inputs are
  reserved (rejected). Artifacts are written only inside the configured
  workspace root (path traversal rejected).
- **Honesty.** The Python sandbox is a restricted execution environment, not a
  hardened boundary against adversarial introspection — verified by tests that
  recover the real builtins and read a file (see
  [`docs/architecture/python-sandbox.md`](docs/architecture/python-sandbox.md)).

## Workflow orchestration (Phase 7)

- **No privilege escalation.** A workflow never escalates its own privileges:
  a run with `ANALYZE`-class capabilities cannot invoke `EXECUTE`/`DESTRUCTIVE`
  without explicit policy authorization, and a stage cannot bypass the Research
  Runtime permission model.
- **No arbitrary tool chains.** The model cannot submit a free-form sequence of
  tool names for execution — the workflow engine validates stage types and
  dependencies against registered workflows/templates.
- **Deterministic only.** Phase 7 executes no model code; the synthesis step is
  a provider-neutral `SynthesisRequest` boundary, not an inference call.
- **Bounded execution.** Guardrails (`max_stages`, `max_retrieval_rounds`,
  `max_verification_rounds`, `max_computation_rounds`, `max_tool_calls`) bound
  loops and resource use; failures produce explicit states, never fabricated
  completion.

## Inference boundary (Phase 8)

- **Credentials isolated.** Qwen API credentials are referenced by
  environment-variable name and resolved only inside the provider adapter; they
  never appear in domain objects, `ResearchState`, memory, artifacts, MCP
  arguments, model context, workflow events, logs, or serialized requests. MCP
  never receives provider credentials.
- **No privilege/endpoint mutation by the model.** Provider configuration is
  operator-controlled; model-generated content cannot select arbitrary
  credentials, change endpoints, or alter security policy.
- **No hidden reasoning.** Hidden chain-of-thought / internal thinking is never
  persisted or returned; only bounded reasoning metadata is recorded.
- **No autonomous tool execution.** Tool calls are normalized and returned to
  the Research Runtime; they are never executed by the provider adapter
  (execution requires the Research Runtime's permission model — Phase 9+).
- **Retries/timeouts.** Retries apply only to known transient failures; auth,
  invalid, and content-rejection errors are never retried. Timeouts are
  enforced per provider, including a real `stream_idle_seconds` idle timeout on
  streamed responses.
- **Model-specific discovery (Phase 8.1).** Capability discovery is driven by
  an operator-overridable, static model catalog; unknown model ids resolve
  conservatively (no reasoning assumed) rather than trusting a blanket family
  claim.
- **Structured-output validation (Phase 8.1).** Provider output is validated
  against the requested JSON Schema before being returned; non-conforming
  output raises `StructuredOutputError` instead of being accepted.
- **Built-in tools are cataloged, never invoked (Phase 8.3).** Qwen built-in
  web search / code interpreter / web scraping are recorded in the catalog as
  provider-native facts but are **never** invoked and are **never** exposed as
  if they were MCP tools. Only the Research Runtime's own tool permission model
  (Phase 9+) may execute tools.
- **Availability resolution is honest (Phase 8.3).** A model is not assumed
  available on every endpoint; the provider resolves model + endpoint + region
  + plan and raises distinct errors rather than silently substituting a model.
  No unsafe operator override is invisible — the diagnostic records the
  capability source (catalog vs operator override vs provider discovery).

## Hidden chain-of-thought

The system **never** stores, transmits, logs, or exposes hidden
chain-of-thought. The persistence layer structurally has no field for it.
Multi-turn continuation carries prior-turn `reasoning_content` only as a
**transient** in-memory field (`Message.reasoning_content`, marked
`transient`), which the serializer skips — it is never persisted or returned to
the Research Runtime.

## Reporting

This is a local, single-user system under active architecture development. For
issues, open a GitHub issue on the repository; do not include secrets.

## Scope of early phases

Authentication / multi-user RBAC is explicitly out of scope for the initial
implementation phases (single-user local-first). The permission boundary is
designed to be forward-compatible with adding auth later without redesign.
