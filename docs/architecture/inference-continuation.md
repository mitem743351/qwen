# Inference Continuation (Phase 9)

How a tool-call turn is continued in the **same** inference session.

---

## Continuation message construction

After executing tool calls, the loop appends, in order:

```text
assistant message (tool_calls=[…], reasoning_content=transient)
tool message (tool_call_id, content)          ← one per executed call
```

The original assistant tool-call message **remains** in history; tool results
are appended after it, preserving the sequence:

```text
user → assistant(tool_calls) → tool(result) → assistant(next)
```

Tool results are wrapped as controlled `role=tool` messages; raw tool output is
never concatenated into system/developer instructions (it is DATA, not
AUTHORITY).

### Multi-tool batch invariant (Phase 9.2)

Every assistant `tool_calls` message that enters a continuation must have
exactly one `role=tool` result message for **every** call in it, associated by
`tool_call_id`. A batch that is partially executed (denied/invalid/over-budget)
still produces an explicit outcome for each call — `CANCELLED` /
`RESOURCE_LIMIT` for the unexecuted remainder — so no tool call is ever left
dangling. A duplicated `call_id` is never executed twice (idempotency via
`inference_session_id` + `call_id`).

---

## Preserved reasoning state

For models requiring preserved reasoning (`qwen3.8-max-preview`,
`qwen3.7-max`), the assistant message carries the provider's
`reasoning_content`. This is **transient**:

- Carried only in the in-memory `InferenceConversation` and the next request's
  messages.
- Marked `transient` on `Message.reasoning_content` and
  `InferenceResult.reasoning_content`, so the serializer never persists it.
- Never placed in Memory, ResearchContext, MCP results, workflow events,
  SQLite, or logs.

Missing-reasoning validation is model-specific (Phase 8.5): strict for
thinking-forced models, permissive for hybrid models.

---

## Conversation & session identity

- `InferenceSession` — stable safe identity (`inference_session_id`, task,
  provider, model, mode, created_at). A continuation stays in the same session.
- `InferenceConversation` — ephemeral runtime state (messages, turn count,
  token usage, continuation count). Hidden reasoning is never persisted; only
  safe metadata is.

---

## Context growth management

Each tool call grows context. The loop is bounded: tool output is serialized
with a size cap, and the loop's `max_context_size` / `max_output_tokens` are
hard limits. Only safe tool outputs / retrieved evidence are compressed;
hidden reasoning is never summarized.

---

## Accounting & observability

`LoopAccounting` aggregates `inference_calls`, `tool_calls`, `tool_failures`,
`tool_denials`, `loop_turns`, `input_tokens`, `output_tokens`, `duration_ms`.
Safe structured events are emitted
(`INFERENCE_STARTED` … `TOOL_DENIED` … `LOOP_LIMIT`) — never hidden reasoning,
API keys, raw private prompts, or full document contents.

See [`tool-loop.md`](tool-loop.md).
