# Gateway Inference (Phase 9)

Enabling the controlled tool-call loop for GATEWAY_INFERENCE mode.

---

## Environment

| Variable | Meaning |
|----------|---------|
| `QWEN_RESEARCH_ENABLE_INFERENCE` | `"1"` to enable the inference runtime |
| `DASHSCOPE_API_KEY` | Qwen API key (Bearer) |
| `QWEN_RESEARCH_INFERENCE_ENDPOINT` | endpoint override |
| `QWEN_RESEARCH_INFERENCE_MODEL` | default model (default `qwen3.7-max`) |
| `QWEN_RESEARCH_INFERENCE_ENDPOINT_PROFILE` | endpoint profile id (e.g. `token-plan`) |
| `QWEN_RESEARCH_INFERENCE_PLAN` | availability plan (e.g. `token_plan`) |
| `QWEN_RESEARCH_INFERENCE_REGION` | region selector |

The tool loop is invoked through the Research Runtime:

```text
Research Task → ResearchContext → SynthesisRequest → InferenceRequest
  → run_tool_loop() → Qwen ↔ tool calls ↔ Research Runtime → final result
```

---

## Tool policy

The default profile is `ANALYSIS` (READ + ANALYZE tools). WRITE/EXECUTE/
DESTRUCTIVE tools are disabled unless a task policy explicitly opts in via
`RESEARCH` (which adds selected WRITE). `run_python` is never model-callable.

Tool execution always goes through the internal tool registry / application
APIs — never through the provider and never via MCP transport hops.

---

## Live test (opt-in)

```text
QWEN_LIVE_TEST=1 DASHSCOPE_API_KEY=... pytest tests/inference/test_live.py
```

Never required for normal validation. The tool-loop path is covered by
deterministic fake-provider tests (no credentials).

See [`../architecture/tool-loop.md`](../architecture/tool-loop.md).
