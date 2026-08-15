# Inference Runtime

Phase 8 introduces the **actual Inference Runtime**: a strict, provider-neutral
boundary beneath the Research Runtime, beginning with Qwen.

> **Objective:** connect the Research Runtime to real model providers through a
> provider-neutral inference boundary — one reliable, observable inference call.

Module: `python/qwen_research/inference/`.

---

## Boundary

```text
Research Runtime
    ↓ InferenceRequest
Inference Runtime      (provider selection, negotiation, retry, timeout, usage)
    ↓
Provider Adapter       (QwenProvider — translates to Qwen's API)
    ↓
Qwen API
    ↓ InferenceResult
Research Runtime
```

The dependency rule is **never** `Research Runtime → Qwen SDK directly` and
**never** `MCP → Qwen API`. The inference runtime is an adapter *beneath* the
Research Runtime.

---

## Responsibility split

```text
Research Runtime  = decides what inference is needed
Inference Runtime = decides how to invoke the provider
Qwen Provider     = translates to Qwen's API
Qwen              = performs actual model inference
```

The `InferenceRuntime` owns provider selection, capability negotiation, request
validation, timeout and retry handling, response normalization, usage
accounting, and provider metadata. It does **not** own research planning,
retrieval, memory, verification, workflow orchestration, or claim management.

---

## Provider abstraction

The authoritative `InferenceProvider` protocol (Phase 1) is the single
abstraction — no second interface was created:

```text
capabilities() · model_info() · generate() · stream() · structured_output()
```

`QwenProvider` implements it, and `InferenceRuntime` wraps it with negotiation
and retry.

---

## Capability negotiation

```text
ReasoningProfile → InferencePolicy → negotiate() → NegotiationResult
    ├── provider_policy          (what the backend actually receives)
    └── workflow_emulation_plan  (external work for emulated capabilities)
```

The provider receives only parameters it actually supports; emulated
capabilities are never emitted as fake native parameters (Phase 1.2 preserved).
`InferencePolicy.model_requirement` remains the single model-selection
authority. Negotiation is now fed **model-specific** capabilities and limits
(`provider.capabilities(model)` / `provider.limits(model)`), so a reasoning
budget is applied natively on models that support it and emulated elsewhere.

---

## Streaming & structured output

- `stream()` yields normalized `InferenceStreamEvent` values (text/tool deltas,
  usage, terminal) — never provider-specific SSE. The transport reads the body
  **incrementally** and enforces a genuine `stream_idle_seconds` idle timeout
  between chunks (`ProviderTimeoutError` on a stall).
- `structured()` requests a `StructuredOutputSpec`; the returned JSON is
  validated **against the requested schema** (bounded JSON Schema subset).
  Invalid output raises a `StructuredOutputError` rather than being returned.

---

## Retries & timeouts

Retries apply **only** to known transient failures (429, 5xx, connection reset)
with exponential backoff; auth/invalid/content errors are never retried.
Separate timeouts (connection / request / stream-idle) are configured per
provider, and `stream_idle_seconds` now actually gates the gap between streamed
chunks.

---

## Usage, finish reasons, hidden reasoning

- Usage is captured where available (`input_tokens`/`output_tokens`/
  `total_tokens`); reasoning-token fields are never assumed.
- Finish reasons are normalized (`stop`/`length`/`tool_calls`/
  `content_filter`/`error`/`unknown`); `length` is never presented as complete.
- Hidden chain-of-thought is **never** persisted or returned; only bounded
  reasoning metadata (requested/supported/budget) is recorded.

---

## Persistence

`SqliteInvocationStore` persists invocation **metadata** (provider, model,
profile, status, usage, finish reason, capability decisions, timestamps,
retry count) — never secrets, private prompts, or hidden reasoning.

See [`providers.md`](providers.md), [`qwen-provider.md`](qwen-provider.md), and
[`../setup/inference.md`](../setup/inference.md).
