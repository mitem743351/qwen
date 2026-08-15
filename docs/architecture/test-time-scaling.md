# Test-Time Compute Scaling (Phase 10)

Phase 10 transforms the system from *single useful inference + controlled tool
loop* into *bounded high-effort research execution*.

XHIGH/EXTREME mean **more bounded useful work** — never longer prompts, higher
temperature, more permissions, or hidden-reasoning storage.

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

- **Reserve → execute → commit**: an operation must reserve before spending.
- `consumed` is monotonic — a restart cannot reset it.
- Global ceilings are authoritative; nested trajectories inherit remaining
  budget and can never exceed the top-level ceiling.

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
