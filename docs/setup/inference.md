# Enabling inference (Qwen)

The Inference Runtime is disabled by default; enabling it connects the Research
Runtime to the Qwen backend through the provider-neutral boundary. Credentials
are read from the environment and are **never** exposed to MCP or persisted.

---

## Environment variables

| Variable | Meaning |
|----------|---------|
| `QWEN_RESEARCH_ENABLE_INFERENCE` | `"1"` to enable the inference runtime |
| `DASHSCOPE_API_KEY` | Qwen API key (Bearer; required at invocation) |
| `QWEN_RESEARCH_INFERENCE_ENDPOINT` | optional endpoint override (default `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`) |
| `QWEN_RESEARCH_INFERENCE_ENDPOINT_PROFILE` | optional endpoint profile id (e.g. `token-plan`) |
| `QWEN_RESEARCH_INFERENCE_PLAN` | optional availability plan (e.g. `token_plan`) |
| `QWEN_RESEARCH_INFERENCE_REGION` | optional region selector |
| `QWEN_RESEARCH_INFERENCE_MODEL` | optional default model (default `qwen3.7-max`) |
| `QWEN_RESEARCH_INFERENCE_CREDENTIAL_ENV` | optional credential env-var name override |
| `QWEN_RESEARCH_INFERENCE_DB` | optional SQLite path for invocation metadata |

---

## Example (Qwen Studio MCP config)

```json
{
  "mcpServers": {
    "qwen-research": {
      "command": "python",
      "args": ["-m", "qwen_research.mcp"],
      "cwd": "/path/to/qwen-research-system",
      "env": {
        "QWEN_RESEARCH_ENABLE_INFERENCE": "1",
        "DASHSCOPE_API_KEY": "<your-key>",
        "QWEN_RESEARCH_INFERENCE_MODEL": "qwen3.7-max"
      }
    }
  }
}
```

The credential lives only in the MCP launch environment; the model and MCP tool
payloads never contain it.

---

## Model selection & capability discovery

Model capabilities and availability are discovered **per model and per
context** from the catalog in `python/qwen_research/inference/providers/`
(`qwen_models.py` + `qwen_availability.py`). Availability is resolved from:

```text
model + endpoint + region + plan + inference mode → effective availability + capabilities
```

Select a model with `QWEN_RESEARCH_INFERENCE_MODEL` or a per-request
`model_requirement`; scope it with `QWEN_RESEARCH_INFERENCE_ENDPOINT_PROFILE`,
`QWEN_RESEARCH_INFERENCE_PLAN`, and `QWEN_RESEARCH_INFERENCE_REGION`. An unknown
model id is passed through conservatively (no reasoning assumed); a model that
exists but is not reachable under the configured endpoint/plan/region raises a
distinct error (`ModelEndpointUnavailableError` / `ModelPlanUnavailableError` /
`ModelRegionUnavailableError`), not `ModelNotFoundError`.

Qwen3-era thinking models (e.g. `qwen3.7-max`) accept a numeric `thinking_budget`
via the reasoning profile's budget; the Qwen2.5-era `qwen-max`/`qwen-turbo`
hybrid models support `enable_thinking` but not a numeric budget. The preview
`qwen3.8-max-preview` is **Token Plan only** — configure its endpoint profile /
plan / credential explicitly.

```yaml
providers:
  qwen:
    endpoint_profile: token_plan
    region: global
    plan: token_plan
    model: qwen3.8-max-preview
    credential_env: BAILIAN_TOKEN_PLAN_API_KEY
```

(Secrets are placeholders; never commit real values.)

---

## Usage

The Research Runtime exposes `invoke_inference` / `stream_inference` /
`synthesize` (Phase 8 application boundary). The single-invocation
`GATEWAY_INFERENCE` flow is:

```text
Research Task → ResearchContext → SynthesisRequest → InferenceRequest
  → Inference Runtime → Capability Negotiation → Qwen Provider → Qwen API
  → InferenceResult → Research Runtime
```

`STUDIO_NATIVE` mode does **not** route through this runtime (Qwen Studio owns
its native inference); `HYBRID` escalation is not yet implemented.

---

## Live smoke test (opt-in)

```text
QWEN_LIVE_TEST=1 DASHSCOPE_API_KEY=... pytest tests/inference/test_live.py
```

This is **never** required for normal validation.

See [`../architecture/inference-runtime.md`](../architecture/inference-runtime.md).
