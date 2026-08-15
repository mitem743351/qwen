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
- **Models** — the Qwen3.x flagships (`qwen3.8-max`, `qwen3.7-max`,
  `qwen3.7-plus`, `qwen3.6-plus`, …), the Qwen2.5-era aliases (`qwen-max`,
  `qwen-plus`, `qwen-turbo`, `qwen-flash`), and the reasoning-only `qwq-*`
  models. The full line-up lives in `qwen_models.py`.
- **Request** — `/chat/completions` with `model`, `messages`, `temperature`,
  `top_p`, `max_tokens`, `stream`, `tools` (full function schemas),
  `response_format`, `enable_thinking`, and — on Qwen3-era thinking models —
  a numeric `thinking_budget`.
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
(`context_window`, `max_output_tokens`, `thinking`, `thinking_budget`); the
adapter's `capabilities(model)` / `limits(model)` / `model_info(model)` resolve
against it. Unknown model ids resolve conservatively (no reasoning, unknown
context) rather than assuming a capability.

| Model | Context | thinking | thinking_budget |
|-------|---------|----------|-----------------|
| `qwen3.8-max` / `qwen3.7-max` / `qwen3.7-plus` | 1M | yes | **yes** |
| `qwen3.6-plus` / `qwen3.5-plus` / `qwen3-max` | varies | yes | **yes** |
| `qwen-plus` | 128K | yes (hybrid) | no |
| `qwen-max` | 32K | yes (hybrid) | no |
| `qwen-turbo` / `qwen-flash` | 128K | no | no |
| `qwq-plus` / `qwq-32b` | 128K | yes (always) | **yes** |

The catalog is **operator-overridable** (`QwenProvider(..., model_catalog=…)`).

---

## Capability mapping

| Capability | Advertised | Notes |
|-----------|-----------|-------|
| reasoning | model-specific | `enable_thinking`; hybrid vs thinking-only per model |
| reasoning budget | model-specific | numeric `thinking_budget` on Qwen3-era thinking models |
| max output tokens | supported | `max_tokens` |
| temperature / top_p | supported | — |
| tool calling | supported | full function schemas (name + description + JSON Schema) |
| structured output | supported | `response_format` json_object; validated against the requested schema |
| streaming | supported | SSE, incremental read with idle timeout |
| parallel generation / context caching / preserved thinking | unsupported | — |

Unsupported required capabilities are `REJECT`ed by negotiation; unsupported
optional ones `DEGRADE`/`EMULATE`.

---

## Request mapping

`InferenceRequest` (and its prepared `messages`) is mapped to the Qwen request
shape inside `QwenProvider._build_request`. Provider-specific field names
(`max_tokens`, `enable_thinking`, `thinking_budget`, `response_format`) never
leave the adapter. Full `ToolSpec` definitions (name, description, argument
JSON Schema) are passed through — tool **execution** remains a later phase.

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
requested/supported" (and the requested budget) is recorded.
