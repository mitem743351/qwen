# Controlled Tool-Calling Loop (Phase 9)

The transition from a single inference call to **controlled model ↔ Research
Runtime interaction**: Qwen may request tools, the Research Runtime authorizes
and executes them through the internal tool registry, and the same inference
session continues with normalized tool results.

Module: `python/qwen_research/research/tool_loop.py`.

---

## Execution model

```text
Qwen
  ↓ InferenceResult (final content + ToolCall[])
  ↓
Research Runtime
  ├── Policy check (profile + permissions + allowlist)
  ├── Argument validation (shared JSON-Schema validator)
  ├── Tool registry lookup
  ├── Tool execution (application API only)
  ↓ ToolExecutionResult
  ↓ append continuation messages (assistant tool_calls + tool results)
  ↓
Qwen (next turn)
```

The **provider** only performs HTTP, Qwen request mapping, response
normalization, streaming, and provider errors. The **Research Runtime** owns
tool authorization, execution, continuation, loop limits, state, permissions,
and workflow accounting. `QwenProvider` never invokes a tool directly, and the
model never touches filesystem/SQL/subprocess.

---

## Tool definition model

`ToolSpec` (Phase 8) is the authoritative provider-neutral definition
(`name`, `description`, `parameters`). The internal `Tool` adds `permission`
and `model_callable`; the Research Runtime additionally carries an executor
(the runtime method) and availability. There is no second tool-definition
model: MCP schemas and Qwen `ToolSpec`s are projections of the same registry.

---

## Authorization (six checks)

Every model-generated tool call must pass, in order:

1. tool exists (registry lookup)
2. tool is enabled (`model_callable`)
3. permission is allowed (profile `allowed_permissions`)
4. tool is allow-listed (profile `allowed_tools`)
5. arguments validate against the tool schema (shared validator)
6. resource policy permits (repeated-call guard, budgets)

Only after all six does execution happen. Tool arguments are validated with the
same JSON-Schema validator used for structured output — no second validator.

Malformed Qwen tool arguments are **never silently normalized to `{}`**: the
provider records `ToolCall.arguments_error`, and the loop returns
`INVALID_ARGUMENTS` without executing (Phase 9.1).

---

## Trusted scope injection

`ToolExecutionRequest` separates model-supplied fields (`call_id`,
`tool_name`, `arguments`) from **trusted context** (`project_id`, `session_id`,
`task_id`, `run_id`), which the runtime injects. The model can never choose the
project/session scope — a model-supplied `project_id` is overwritten by the
trusted value before execution.

---

## Profiles

| Profile | Permissions | Notes |
|---------|-------------|-------|
| `READ_ONLY` | READ | observation only |
| `ANALYSIS` (default) | READ + ANALYZE | read + run deterministic queries/analyses |
| `RESEARCH` | READ + ANALYZE + selected WRITE | adds `save_research_memory` |

`run_python` is **never** model-callable (EXECUTE); `DESTRUCTIVE` is disabled
everywhere. WRITE is opt-in via the `RESEARCH` profile.

---

## Loop budgets

Every loop has hard limits (`ToolLoopConfig`): `max_turns`, `max_tool_calls`,
`max_same_tool_calls`, `max_total_tool_duration_ms`,
`max_total_wall_time_ms`, `max_output_tokens`, `max_context_size`. A repeated
identical call (normalized `tool_name + arguments` hash) is bounded by
`max_same_call` (default 2) — exceeding it yields `RESOURCE_LIMIT`.

---

## Multi-tool batches (Phase 9.2)

A single inference response may carry several tool calls. Each call is
validated **immediately before its own execution** (parse → resolve →
model-callable → permission/allowlist → schema → budget) — the batch is not
pre-validated all at once. The default policy is `ALL_OR_EXPLICITLY_PARTIAL`:
execution proceeds in order and stops at the first unsafe call, but **every
call receives exactly one outcome**:

```text
call_1 → SUCCEEDED
call_2 → DENIED / INVALID_ARGUMENTS   (unsafe point)
call_3 → CANCELLED                     (never executed, still represented)
```

Budget exhaustion is the same shape: calls past `max_tool_calls` get an explicit
`RESOURCE_LIMIT` result rather than being silently dropped. No assistant
`tool_calls` message ever enters a continuation with a dangling call. When a
batch is partial and `continue_after_partial` is `False`, the loop returns
`TOOL_EXECUTION_PARTIAL` with the safe accumulated results.

`TOOL_LOOP_LIMIT` means an actual loop/budget limit only — it is never used to
represent an ordinary tool failure. A duplicated `call_id` within a session is
never executed twice (idempotency).

---

## Tool results

- `ToolExecutionResult` statuses: `SUCCEEDED`, `FAILED`, `DENIED`,
  `INVALID_ARGUMENTS`, `TIMEOUT`, `UNAVAILABLE`, `RESOURCE_LIMIT`, `CANCELLED`.
- `ToolError` codes: `INVALID_ARGUMENTS`, `NOT_FOUND`, `PERMISSION_DENIED`,
  `UNAVAILABLE`, `TIMEOUT`, `RESOURCE_LIMIT`, `CANCELLED`, `INTERNAL_ERROR`.
- Errors never expose filesystem paths, stack traces, credentials, or SQL.
- Tool output is serialized to a **bounded** content string (default 4 KB) and
  treated as DATA, never AUTHORITY.

## Loop outcome

`LoopStatus`: `FINAL`, `TOOL_LOOP_LIMIT`, `TIME_LIMIT`, `CONTEXT_LIMIT`,
`PERMISSION_DENIED`, `PROVIDER_ERROR`, `TOOL_ERROR`,
`TOOL_EXECUTION_PARTIAL`, `TOOL_BATCH_REJECTED`. A `finish_reason=length` turn
is **not** a complete final answer — the provider's finish reason is preserved.

## Persistence & idempotency (Phases 9.3–9.4)

Completed tool results are persisted through a `ToolExecutionStore` keyed by
`(inference_session_id, call_id)`. Phase 9.4 makes execution **transactional**:
each call is atomically claimed (lease-based), executed, and durably completed.
A resumed workflow replays a terminal result instead of executing the same call
twice; a crash-ambiguous outcome is recorded as `UNKNOWN` and never silently
retried for side-effecting tools. Only safe metadata is stored; hidden
reasoning is never persisted. See
[`tool-execution-reliability.md`](tool-execution-reliability.md).

See [`inference-continuation.md`](inference-continuation.md) and
[`../setup/gateway-inference.md`](../setup/gateway-inference.md).
