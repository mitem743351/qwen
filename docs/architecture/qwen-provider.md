# Qwen Provider

The first production provider adapter.

Module: `python/qwen_research/inference/providers/qwen.py`; model catalog in
`python/qwen_research/inference/providers/qwen_models.py`.

---

## Verified API contract (2026)

The adapter targets the Qwen **OpenAI-compatible** chat-completions API:

- **Endpoint** — `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  (international) or `https://dashscope.aliyuncs.com/compatible-mode/v1` (CN).
- **Auth** — `Authorization: Bearer <DASHSCOPE_API_KEY>` (key via the
  `DASHSCOPE_API_KEY` environment variable).
- **Models** — the Qwen3.x flagships (`qwen3.7-max`, `qwen3.7-plus`,
  `qwen3.6-plus`, …), the Qwen2.5-era aliases (`qwen-max`, `qwen-plus`,
  `qwen-turbo`, `qwen-flash`), and the reasoning-only `qwq-*` models. The full
  line-up lives in `qwen_models.py`.
- **Request** — `/chat/completions` with `model`, `messages`, `temperature`,
  `top_p`, `max_tokens`, `stream`, `tools` (full function schemas),
  `response_format`, `enable_thinking`, and — on the models that support them —
  a numeric `thinking_budget` and `preserve_thinking`.
- **Streaming** — SSE chunks with `choices[0].delta.content`, `finish_reason`,
  and `usage` (with `stream_options.include_usage`); read incrementally with a
  real `stream_idle_seconds` idle timeout.
- **Finish reasons** — `stop`, `length`, `tool_calls`, `content_filter`.
- **Usage** — `prompt_tokens`, `completion_tokens`, `total_tokens`.

Only documented parameters are emitted; no undocumented parameters are
hard-coded.

---

## Model-specific capability discovery

Capability discovery is **per model**, not a single blanket for the family.
`qwen_models.py` maps each model id to a `QwenModelSpec`
(`context_window`, `max_output_tokens`, `thinking`, `thinking_budget`,
`preserve_thinking`, `structured_output`, `tool_calling`, `streaming`); the
adapter's `capabilities(model)` / `limits(model)` / `model_info(model)` resolve
against it. Unknown model ids resolve conservatively (no reasoning, unknown
context) rather than assuming a capability.

| Model | Context | thinking | budget | preserve_thinking | structured output | tool calling |
|-------|---------|----------|--------|-------------------|-------------------|--------------|
| `qwen3.7-max` | 1M | yes | **yes** | **yes** | yes | yes |
| `qwen3.7-plus` | 1M | yes | **yes** | **yes** | yes | yes |
| `qwen3.6-plus` / `qwen3.5-plus` / `qwen3-max` | varies | yes | **yes** | no | yes | yes |
| `qwen-plus` | 128K | yes (hybrid) | **yes** | no | yes | yes |
| `qwen-max` | 32K | yes (hybrid) | no | no | yes | yes |
| `qwen-turbo` / `qwen-flash` | 128K | no | no | no | yes | yes |
| `qwq-plus` / `qwq-32b` | 128K | yes (always) | no | no | **no** | **no** |

Streaming is supported by all listed models. `qwen3.7-max` has a documented
**65,536** max output tokens.

The catalog is **operator-overridable** (`QwenProvider(..., model_catalog=…)`).

> **Note:** `qwen3.8-max` was deliberately **removed** from the catalog: at the
> time of this snapshot it was only available in preview / via the Token Plan
> and its capability matrix had not been confirmed against official docs. See
> "Catalog maintenance" below.

---

## Capability mapping

| Capability | Advertised | Notes |
|-----------|-----------|-------|
| reasoning | model-specific | `enable_thinking`; hybrid vs thinking-only per model |
| reasoning budget | model-specific | numeric `thinking_budget` on Qwen3-era thinking models |
| preserved thinking | model-specific | `preserve_thinking` on `qwen3.7-max`/`qwen3.7-plus` only |
| max output tokens | supported | `max_tokens` |
| temperature / top_p | supported | — |
| tool calling | model-specific | full function schemas; **not** on thinking-only `qwq-*` |
| structured output | model-specific | `response_format` json_object; validated against the requested schema; **not** in thinking mode / on `qwq-*` |
| streaming | supported | SSE, incremental read with idle timeout (all chat models) |
| parallel generation / context caching | unsupported | — |

Unsupported required capabilities are `REJECT`ed by negotiation; unsupported
optional ones `DEGRADE`/`EMULATE`.

---

## Request mapping

`InferenceRequest` (and its prepared `messages`) is mapped to the Qwen request
shape inside `QwenProvider._build_request`. Provider-specific field names
(`max_tokens`, `enable_thinking`, `thinking_budget`, `preserve_thinking`,
`response_format`) never leave the adapter. Full `ToolSpec` definitions (name,
description, argument JSON Schema) are passed through — tool **execution**
remains a later phase.

## Response normalization

`InferenceResult` carries normalized `content`, `structured_output`,
`tool_calls_structured`, `usage`, `finish_reason`, and `provider`. A
`finish_reason = length` result is marked with a warning, never "complete".

## Structured-output validation

When a schema is requested, the adapter validates the returned JSON **against
that schema** (a bounded, dependency-free JSON Schema subset: `type`,
`properties`, `required`, `items`, `enum`, `const`). Non-conforming output
raises `StructuredOutputError` instead of being returned as valid.

## Hidden reasoning

Qwen thinking/reasoning content is treated as **hidden internal reasoning** and
is never persisted or returned. Only the bounded fact "reasoning was
requested/supported" (and the requested budget) is recorded. `preserve_thinking`
is passed through as an opaque provider flag only; the reasoning content itself
is never surfaced to the domain model.

---

## Catalog maintenance

`qwen_models.py` is a **snapshot**, not a live query, and must be re-verified
against the official QwenCloud / Alibaba Model Studio model pages whenever the
line-up changes. The maintenance process is:

1. **Re-verify each field** against official docs (QwenCloud "Thinking",
   "Structured output", and Model Studio "Use deep thinking models via API" /
   API reference), not third-party summaries.
2. **Prefer conservative values** — leave a capability `False` (or a bound
   `None`) rather than asserting something unconfirmed.
3. **Remove unverified entries** — e.g. `qwen3.8-max` was removed because its
   capability matrix was only preview / not confirmed (Phase 8.2).
4. **Update the tests** in `tests/inference/test_qwen_models.py`, especially
   `test_qwen_37_max_documented_capabilities`, to pin the documented facts.

A model's `thinking` / `thinking_budget` / `preserve_thinking` /
`structured_output` / `tool_calling` / `streaming` flags all flow through
`QwenProvider.capabilities(model)` into capability negotiation, so an incorrect
catalog entry is an incorrect negotiation claim — keep it honest.
