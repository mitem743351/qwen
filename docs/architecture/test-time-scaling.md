# Test-Time Compute Scaling (Phase 10)

Phase 10 transforms the system from *single useful inference + controlled tool
loop* into *bounded high-effort research execution*.

XHIGH/EXTREME mean **more bounded useful work** — never longer prompts, higher
temperature, more permissions, or hidden-reasoning storage.

Phase 10.1 replaces the callback-only engine with a **real** Research Runtime
integration. Phase 10.2 turns it into **enforcement**: the `HighEffortEngine`
drives the runtime's `search_corpus` / `create_claim` / `verify_claim` /
`get_contradictions` / `run_analysis` / `invoke_inference` / `run_tool_loop`
directly, with **admission-before-execution** (budget + deadline), bounded
child limits derived from the remaining global budget, an absolute persisted
wall-clock deadline, checkpoint-after-every-stage, an honest trajectory state
machine, and a real draft→critique→action→revision→final-verification loop.
The profile's native reasoning intent flows
`profile → InferencePolicy → Qwen reasoning translator → request`.

---

## Two dimensions, kept separate

```text
Qwen-native inference effort  ≠  Research-runtime test-time computation
```

- **Native reasoning** (`reasoning_effort` / `thinking_budget`) is a *provider*
  control over hidden reasoning depth.
- **Test-time compute** (retrieval, verification, computation, trajectories,
  critique, synthesis) is the *workflow* work the runtime performs.

Both are independently bounded.

---

## Budget model

`TestTimeComputePolicy` gives each profile explicit numeric ceilings (no
`None`/infinite defaults). `TestTimeComputeBudget` tracks
`allocated` / `consumed` / `remaining` per `ResourceDimension`:

```text
inference_calls, inference_turns, tool_calls, retrieval_rounds,
retrieval_candidates, verification_rounds, computation_rounds, trajectories,
critique_rounds, synthesis_passes, wall_time, tokens
```

- **Admission ≠ accounting**: the engine admits (reserves) a unit *before* the
  child runs, passes a bounded child limit (`max_output_tokens`, retrieval
  `limit`, tool-loop `max_tool_calls`) derived from the *remaining* budget, and
  commits *actual* consumption after. Overruns are flagged as violations, never
  silently clamped.
- `consumed` is monotonic — a restart cannot reset it.
- Global ceilings are authoritative; nested trajectories inherit remaining
  budget and can never exceed the top-level ceiling.
- An **absolute wall-clock deadline** (`deadline_at`) is persisted; a restart
  resumes with the remaining time, never a fresh window.
- The full **logical run state** is checkpointed after every durable transition
  (stage, trajectory, critique decision, draft version, reallocation) and
  resumed — a completed stage is never re-run merely because of a restart.

## Scheduler

`TestTimeScheduler` reallocates *remaining* (never consumed) budget
deterministically and observably. Rules: never exceed global ceilings, never
make consumed budget available again, reallocation is recorded, and the model
can never increase budget.

## Profiles

| Profile | tool_calls | trajectories | retrieval | verification | critique |
|---------|-----------|--------------|-----------|--------------|----------|
| FAST    | 4         | 1            | 1         | 0            | 0        |
| NORMAL  | 16        | 1            | 2         | 1            | 1        |
| DEEP    | 32        | 2            | 3         | 2            | 2        |
| XHIGH   | 60        | 3            | 5         | 4            | 3        |
| EXTREME | 120       | 5            | 8         | 6            | 5        |

See [`xhigh.md`](xhigh.md), [`extreme.md`](extreme.md), and
[`adaptive-budgeting.md`](adaptive-budgeting.md).
