# Hybrid Studio/Gateway Orchestration (Phase 9 — contract only)

Phase 9 establishes the **explicit contract** for Studio ↔ Gateway hand-off but
does **not** implement automatic escalation (Phase 10/11).

---

## Modes

- `STUDIO_NATIVE` — Qwen Studio owns its native inference loop; the local
  Research Runtime enhances it via MCP but does not control Studio's hidden
  inference.
- `GATEWAY_INFERENCE` — the gateway owns the loop budget, tool policy,
  continuation, workflow state, and provider policy; Qwen owns actual model
  inference.
- `HYBRID` — the boundary between the two (contract defined here).

---

## Escalation contract

```text
EscalationRequest
    session_id, task_id, reason, target_mode, context_refs, tool_policy

EscalationResult
    status, target_mode, inference_ref
```

`context_refs` are **references** (evidence/computation/memory/artifact ids),
never raw content. `tool_policy` is a tool-execution profile name. There is no
automatic selector yet — `EscalationResult.status` is one of `ACCEPTED` /
`REJECTED` / `ALREADY_IN_TARGET_MODE`.

---

## Transfer boundary

Allowed to cross: user request, safe context, evidence refs, memory summaries,
computation summaries, workflow state, tool policy.

Never allowed: API credentials, hidden reasoning, internal secrets,
unrestricted filesystem paths. `validate_transfer()` rejects forbidden fields
(`api_key`, `credential(s)`, `reasoning_content`, `hidden_reasoning`,
`secrets`, `filesystem_path`, `path`, `token`).

---

## Security

The hybrid boundary is the first explicit place where Studio and gateway
contexts meet. The same permission, project/session scoping, and prompt-injection
rules apply on both sides; a model or document can never change application
policy across the boundary.

See [`tool-loop.md`](tool-loop.md) and
[`../setup/gateway-inference.md`](../setup/gateway-inference.md).
