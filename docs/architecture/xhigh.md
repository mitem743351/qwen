# XHIGH Execution (Phase 10)

XHIGH means more bounded, diverse, evidence-oriented work — not "think longer".

## Exact budget

```text
max_inference_calls      = 16
max_inference_turns      = 16
max_tool_calls           = 60
max_retrieval_rounds     = 5
max_retrieval_candidates = 64
max_verification_rounds  = 4
max_computation_rounds   = 4
max_trajectory_count     = 3
max_critique_rounds      = 3
max_synthesis_passes     = 3
max_wall_time_seconds    = 600
max_total_tokens         = 65536
native_reasoning         = reasoning_effort:xhigh
```

## Native Qwen mapping

For a model/endpoint supporting `reasoning_effort` (e.g. `qwen3.8-max-preview`),
XHIGH requests `reasoning_effort=xhigh`. For a `thinking_budget`-only model
(Qwen3.7/3.6/3.5), XHIGH requests a bounded thinking budget. The two controls
are never emitted together.

## Workflow

```text
primary retrieval → alternative retrieval → verification → contradiction search
→ computation → trajectory A → trajectory B → critique → additional evidence
→ revision → final verification → final synthesis
```

Every step consumes explicit bounded resources; early stopping is allowed (the
budget is not a requirement to spend it). See
[`test-time-scaling.md`](test-time-scaling.md).
