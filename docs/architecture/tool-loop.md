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

## Tool results

- `ToolExecutionResult` statuses: `SUCCEEDED`, `FAILED`, `DENIED`,
  `INVALID_ARGUMENTS`, `TIMEOUT`, `UNAVAILABLE`.
- `ToolError` codes: `INVALID_ARGUMENTS`, `NOT_FOUND`, `PERMISSION_DENIED`,
  `UNAVAILABLE`, `TIMEOUT`, `RESOURCE_LIMIT`, `INTERNAL_ERROR`.
- Errors never expose filesystem paths, stack traces, credentials, or SQL.
- Tool output is serialized to a **bounded** content string (default 4 KB) and
  treated as DATA, never AUTHORITY.

## Loop outcome

`LoopStatus`: `FINAL`, `TOOL_LOOP_LIMIT`, `TIME_LIMIT`, `CONTEXT_LIMIT`,
`PERMISSION_DENIED`, `PROVIDER_ERROR`, `TOOL_ERROR`. A `finish_reason=length`
turn is **not** a complete final answer — the provider's finish reason is
preserved.

See [`inference-continuation.md`](inference-continuation.md) and
[`../setup/gateway-inference.md`](../setup/gateway-inference.md).
