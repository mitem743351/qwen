# Qwen Provider

The first production provider adapter.

Modules: `python/qwen_research/inference/providers/qwen.py` (adapter),
`qwen_models.py` (catalog), `qwen_availability.py` (endpoint profiles +
availability resolver + diagnostics).

---

## Verified API contract (2026)

The adapter targets the Qwen **OpenAI-compatible** chat-completions API:

- **Endpoint** — `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  (international) or `https://dashscope.aliyuncs.com/compatible-mode/v1` (CN).
- **Auth** — `Authorization: Bearer <DASHSCOPE_API_KEY>` (key via the
  `DASHSCOPE_API_KEY` environment variable). The Token Plan preview uses its own
  credential (e.g. `BAILIAN_TOKEN_PLAN_API_KEY`) — the credential env name is
  config, never a hard-coded assumption.
- **Models** — the Qwen3.x flagships (`qwen3.7-max`, `qwen3.7-plus`,
  `qwen3.6-plus`, …), the Qwen2.5-era aliases (`qwen-max`, `qwen-plus`,
  `qwen-turbo`, `qwen-flash`), the reasoning-only `qwq-*` models, and the
  official preview `qwen3.8-max-preview` (Token Plan only).
- **Request** — `/chat/completions` with `model`, `messages`, `temperature`,
  `top_p`, `max_tokens`, `stream`, `tools` (full function schemas),
  `response_format`, `enable_thinking`, and — on the models that support them —
  a numeric `thinking_budget` and `preserve_thinking`.

Only documented parameters are emitted; no undocumented parameters are
hard-coded.

---

## Model vs endpoint vs region vs plan vs inference mode

A model id alone does **not** determine availability or capability. The chain
is:

```text
Model identity
  + endpoint / API surface
  + region
  + plan
  + inference mode (thinking)
        ↓
Effective availability + effective capabilities
```

- **`QwenModelSpec`** (catalog) records per-model facts: lifecycle, availability
  class, plans, regions, surfaces, context/output/thinking bounds, and each
  capability flag.
- **`QwenEndpointProfile`** records per-endpoint facts: base URL, region, API
  surface, the plans it serves, and a model allowlist.
- **`QwenModelAvailabilityResolver.resolve(model, endpoint, plan, region)`**
  returns an `AvailabilityResult` (AVAILABLE / PLAN_UNAVAILABLE /
  REGION_UNAVAILABLE / ENDPOINT_UNAVAILABLE / MODEL_UNKNOWN / DEPRECATED).
- **`capabilities(model, thinking_mode=…)`** returns the *effective*
  capabilities for the invocation, gating mode-dependent flags (structured
  output is unavailable while thinking is on).

The standard DashScope endpoint serves only the PUBLIC (GA) line-up; the Token
Plan endpoint is the documented channel for `qwen3.8-max-preview`. A model
appearing in QwenCloud docs is **not** assumed available on every endpoint.

The endpoint profile **controls the network endpoint**: when an endpoint
profile is configured, its `base_url` is the authority for the HTTP call; a raw
`api_endpoint` that disagrees with the profile's `base_url` raises a
`ProviderConfigurationError` rather than being silently ignored.

---

## Transient reasoning_content (multi-turn continuation)

Qwen thinking models return `reasoning_content` on assistant turns. For
`preserve_thinking` multi-turn continuation this hidden reasoning must be passed
back on the next request. The provider-neutral `Message` carries a **transient**
`reasoning_content` field: it is emitted on assistant messages, but it is marked
`transient` so the serializer never persists it and it never reaches the
Research Runtime. When `preserve_thinking` is requested and reasoning is on, a
prior assistant message missing `reasoning_content` raises `InferenceError`
rather than silently dropping the required reasoning state.

---

## Model table (verified snapshot)

| Model | Lifecycle | Availability | Plan | Context | thinking | budget | preserve | structured | tools |
|-------|-----------|--------------|------|---------|----------|--------|----------|------------|-------|
| `qwen3.8-max-preview` | **PREVIEW** | **PLAN_RESTRICTED** | Token Plan | 983,616 | forced | yes | **yes** | **no** | yes |
| `qwen3.7-max` | GA | PUBLIC | — | 1M | hybrid | yes | **yes** | yes | yes |
| `qwen3.7-plus` | GA | PUBLIC | — | 1M | hybrid | yes | **yes** | yes | yes |
| `qwen3.6-plus` / `qwen3.5-plus` / `qwen3-max` | GA | PUBLIC | — | varies | hybrid | yes | no | yes | yes |
| `qwen-plus` | GA | PUBLIC | — | 128K | hybrid | yes | no | yes | yes |
| `qwen-max` | GA | PUBLIC | — | 32K | hybrid | no | no | yes | yes |
| `qwen-turbo` / `qwen-flash` | GA | PUBLIC | — | 128K | no | no | no | yes | yes |
| `qwq-plus` / `qwq-32b` | GA | PUBLIC | — | 128K | forced | no | no | **no** | **no** |

Streaming is supported by all listed models. `qwen3.7-max` has a documented
**65,536** max output; `qwen3.8-max-preview` a **131,072** max output.

`qwen3.8-max-preview` facts (verified): PREVIEW lifecycle, Token Plan only,
**983,616-token** context, always-on thinking with `reasoning_effort`
`low`/`medium`/`xhigh` (**cataloged but not yet executed** — see below),
function calling, and built-in tools (web search, code interpreter, web
scraping). Structured output is **not** available (always-on thinking). Source:
QwenCloud "Qwen Code" (Token Plan) and "Thinking" guides.

### `reasoning_effort` is cataloged, not executed

`qwen3.8-max-preview` documents `reasoning_effort` (`low`/`medium`/`xhigh`) on
the Token Plan endpoint. The adapter records this fact
(`QwenModelSpec.reasoning_effort_levels`) for future use, but **never emits**
`reasoning_effort` in a request — composing it with the XHIGH workflow is
Phase 10. Phase 8.3/8.4 only represent the native provider capability honestly.

---

## Capability mapping

| Capability | Advertised | Notes |
|-----------|-----------|-------|
| reasoning | model-specific | `enable_thinking`; hybrid vs forced per model |
| reasoning budget | model-specific | numeric `thinking_budget` on Qwen3-era thinking models |
| preserved thinking | model-specific | `preserve_thinking` on `qwen3.7-max`/`qwen3.7-plus`/`qwen3.8-max-preview` |
| max output tokens | supported | `max_tokens` |
| temperature / top_p | supported | — |
| tool calling | model-specific | application-defined function schemas; **not** on thinking-only `qwq-*` |
| built-in tools | cataloged, **not invoked** | `qwen3.8-max-preview` web search / code interpreter / web scraping; distinct from function calling |
| structured output | model **and mode** specific | unavailable while thinking is on; validated against the requested schema |
| streaming | supported | SSE, incremental read with idle timeout |
| parallel generation / context caching | unsupported | — |

Unsupported required capabilities are `REJECT`ed by negotiation; unsupported
optional ones `DEGRADE`/`EMULATE`.

---

## Structured-output semantics

Three distinct notions are kept separate:

- **JSON_MODE** — `response_format={"type":"json_object"}` forces valid JSON.
- **STRUCTURED_OUTPUT** — JSON plus conformance to a requested JSON Schema.
- **SCHEMA_VALIDATION** — the adapter re-validates the reply against the schema
  and raises `StructuredOutputError` on mismatch.

The effective `supports_structured_output` capability is gated by inference
mode: it is `False` while thinking is on (or for thinking-only models), matching
Qwen's documented behavior.

---

## Diagnostics

`QwenProvider.diagnose(model, thinking_mode=…, plan=…, endpoint_profile=…)`
returns a `ModelDiagnostic` (model, lifecycle, availability, endpoint, region,
plan, thinking mode, capability source, effective capability flags, notes).
This is the debugging surface for capability negotiation.

---

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
line-up changes. The maintenance rule is:

```text
Official model documentation → catalog update → tests updated → capability behavior verified
```

1. **Re-verify each field** against official docs (QwenCloud "Thinking",
   "Structured output", "Qwen Code" (Token Plan), and Model Studio "Use deep
   thinking models via API" / API reference), not third-party summaries.
2. **Prefer conservative values** — leave a capability `False` (or a bound
   `None`) rather than asserting something unconfirmed.
3. **Do not infer new-model capabilities** by copying a previous model's spec
   unless that approximation is explicitly recorded.
4. **Update the tests** in `tests/inference/test_qwen_models.py`
   (`test_capability_matrix`, `test_qwen_37_max_documented_capabilities`,
   `test_qwen_38_max_preview_is_listed_as_preview`) to pin the facts.
5. **Record `source_urls`** on each spec, and use only official docs as the
   authority (third-party sources are supplemental evidence only).

A model's flags flow through `QwenProvider.capabilities()` into capability
negotiation, so an incorrect catalog entry is an incorrect negotiation claim —
keep it honest.
