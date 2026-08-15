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
| `QWEN_RESEARCH_INFERENCE_MODEL` | optional default model (default `qwen3.7-max`) |
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

Model capabilities are discovered **per model** from the catalog in
`python/qwen_research/inference/providers/qwen_models.py` (context window,
thinking mode, numeric `thinking_budget`). Select a model with
`QWEN_RESEARCH_INFERENCE_MODEL` or a per-request `model_requirement`; an
unknown model id is passed through conservatively (no reasoning assumed) and
only rejected by the API itself. Qwen3-era thinking models (e.g. `qwen3.7-max`)
accept a numeric `thinking_budget` via the reasoning profile's budget; the
Qwen2.5-era `qwen-max`/`qwen-plus` hybrid models support `enable_thinking` but
not a numeric budget.

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
