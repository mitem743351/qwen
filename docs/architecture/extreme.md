# EXTREME Execution (Phase 10)

EXTREME means the maximum *supported* native reasoning plus a larger bounded
workflow budget. It never invents `reasoning_effort=extreme` (which Qwen does
not document), and never grants more permissions.

## Exact budget

```text
max_inference_calls      = 32
max_inference_turns      = 32
max_tool_calls           = 120
max_retrieval_rounds     = 8
max_retrieval_candidates = 128
max_verification_rounds  = 6
max_computation_rounds   = 6
max_trajectory_count     = 5
max_critique_rounds      = 5
max_synthesis_passes     = 4
max_wall_time_seconds    = 1200
max_total_tokens         = 131072
native_reasoning         = reasoning_effort:xhigh
```

## Native Qwen mapping

EXTREME uses the maximum documented native control: `reasoning_effort=xhigh`
where supported, or the maximum bounded `thinking_budget` on budget-only
models. The extra effort comes from the *workflow* budget, not a fabricated
native control.

## Workflow

```text
maximum native reasoning → multiple bounded trajectories → diversified retrieval
→ verification → contradiction search → sensitivity computation
→ independent critique → revision → final verification → final synthesis
```

Every dimension is independently bounded; the global ceiling is authoritative.
See [`test-time-scaling.md`](test-time-scaling.md).
