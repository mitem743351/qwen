# Qwen Provider

The first production provider adapter.

Module: `python/qwen_research/inference/providers/qwen.py`.

---

## Verified API contract (2026)

The adapter targets the Qwen **OpenAI-compatible** chat-completions API:

- **Endpoint** — `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  (international) or `https://dashscope.aliyuncs.com/compatible-mode/v1` (CN).
- **Auth** — `Authorization: Bearer <DASHSCOPE_API_KEY>` (key via the
  `DASHSCOPE_API_KEY` environment variable).
- **Models** — `qwen-max`, `qwen-plus`, `qwen-turbo`, `qwen-flash`, and
  `qwq-*` reasoning models (configured via `default_model` / `model_requirement`).
- **Request** — `/chat/completions` with `model`, `messages`, `temperature`,
  `top_p`, `max_tokens`, `stream`, `tools`, `response_format`, and
  `enable_thinking` (reasoning).
- **Streaming** — SSE chunks with `choices[0].delta.content`, `finish_reason`,
  and `usage` (with `stream_options.include_usage`).
- **Finish reasons** — `stop`, `length`, `tool_calls`, `content_filter`.
- **Usage** — `prompt_tokens`, `completion_tokens`, `total_tokens`.

Only documented parameters are emitted; no undocumented parameters are
hard-coded.

---

## Capability mapping

| Capability | Advertised | Notes |
|-----------|-----------|-------|
| reasoning | supported | `enable_thinking`; discrete, not a numeric budget |
| reasoning budget | **unsupported** | `reasoning_effort` is low/medium/xhigh, not numeric |
| max output tokens | supported | `max_tokens` |
| temperature / top_p | supported | — |
| tool calling | supported | function tools |
| structured output | supported | `response_format` json_object |
| streaming | supported | SSE |
| parallel generation / context caching / preserved thinking | unsupported | — |

Unsupported required capabilities are `REJECT`ed by negotiation; unsupported
optional ones `DEGRADE`/`EMULATE`.

---

## Request mapping

`InferenceRequest` (and its prepared `messages`) is mapped to the Qwen request
shape inside `QwenProvider._build_request`. Provider-specific field names
(`max_tokens`, `enable_thinking`, `response_format`) never leave the adapter.

## Response normalization

`InferenceResult` carries normalized `content`, `structured_output`,
`tool_calls_structured`, `usage`, `finish_reason`, and `provider`. A
`finish_reason = length` result is marked with a warning, never "complete".

## Hidden reasoning

Qwen thinking/reasoning content is treated as **hidden internal reasoning** and
is never persisted or returned. Only the bounded fact "reasoning was
requested/supported" is recorded.
