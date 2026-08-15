# Provider Abstraction & Configuration

The provider layer keeps credentials and provider-specific request/response
shapes out of the domain model and the Research Runtime.

---

## Configuration

```yaml
inference:
  default_provider: qwen
  default_model: qwen-max
  timeout_seconds: 120

providers:
  qwen:
    enabled: true
    endpoint: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    credential_env: DASHSCOPE_API_KEY
```

`ProviderConfig` (typed, serializable) holds `provider_id`, `enabled`,
`api_endpoint`, `credential_env` (an environment-variable **name**, never a
value), `default_model`, timeouts, and retry policy. Qwen-specific fields never
leak into the generic `InferencePolicy`.

---

## Credentials

- Credentials are referenced by environment-variable name (`credential_env`),
  resolved only inside the provider adapter at invocation time.
- A missing credential raises `ProviderCredentialError` **before** any network
  call; the value is never included in errors, logs, memory, artifacts, MCP
  arguments, or serialized requests.
- The MCP layer never receives provider credentials: `MCP → Research Runtime →
  Inference Runtime → credential store/provider config`.

---

## Model selection

`InferencePolicy.model_requirement` is authoritative. The provider maps a
generic requirement to a Qwen model id; an unknown model raises
`ModelNotFoundError` (no silent substitution). Capability discovery is
**model-specific and contextual**: each provider exposes a `models()` catalog
and `capabilities(model, thinking_mode=…)`/`limits(model)`/`model_info(model)`
resolve per model — and per endpoint/plan/inference-mode for Qwen — against a
static, operator-overridable table. `ModelRegistry` caches model metadata with
a TTL so a task does not trigger a network call each time, and can filter by
plan/region/availability.

Availability is **not** global: a model id exists in the catalog, but whether
it is reachable depends on the endpoint, region, and plan. Qwen resolves this
via `QwenModelAvailabilityResolver` (see
[`qwen-provider.md`](qwen-provider.md)), raising distinct errors
(`UnknownModelError`, `ModelPlanUnavailableError`,
`ModelRegionUnavailableError`, `ModelEndpointUnavailableError`) rather than
collapsing everything into `ModelNotFoundError`.

---

## Provider errors

Provider failures are normalized to typed errors and a `ProviderErrorStatus`:

```text
401/403 → AUTH_FAILED       (ProviderAuthError)
429     → RATE_LIMITED      (ProviderRateLimitError)
402     → QUOTA_EXCEEDED    (ProviderRateLimitError)
400     → INVALID_REQUEST   (InferenceError)
5xx     → SERVER_ERROR      (ProviderServerError)
```

Raw stack traces and provider JSON never reach the Research Runtime.

---

## Provider health

`ProviderHealth` is a lightweight, on-demand diagnostic (`available`, `latency`,
`last_error`, `models_available`, `capabilities`) — no continuous pings.

---

## Security

The provider adapter cannot let the model select arbitrary credentials, change
endpoints, or alter security policy. Provider configuration is operator-
controlled; model-generated content never mutates it.
