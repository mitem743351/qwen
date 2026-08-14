# Reasoning Engine

The reasoning architecture: profiles, the policy translation, the workflow
engine, iterative passes, and the rules that keep reasoning auditable without
exposing hidden chain-of-thought.

---

## 1. Core Principle

**Reasoning is an explicit policy system, not a prompt-writing exercise.**

`XHIGH` is not a longer system prompt. It is a named `ReasoningProfile` that the
Workflow Engine and the Inference Adapter jointly enact. The same profile
produces consistent *behavior* regardless of which backend is underneath.

---

## 2. ReasoningProfile Model

```text
ReasoningProfile
    name                 # FAST | NORMAL | DEEP | XHIGH | EXTREME
    planning_depth       # how far the decomposer/planner recurses
    retrieval_depth      # breadth + depth of evidence gathering
    evidence_threshold   # minimum evidence confidence to proceed
    independent_attempts # number of independent reasoning attempts
    critique_passes      # adversarial critique iterations
    verification_passes  # verification checks applied
    context_budget       # token budget allocated to this task
    output_budget        # budget for the response/long-output
    continuation_policy  # how long outputs are continued
    parallelism          # allowed parallel trajectories (future)
```

Profiles are **data**, not code. Adding `EXTREME+` or a custom profile is a
configuration change, not a code change.

### Indicative profile shape (to be tuned, not binding values)

| Field | FAST | NORMAL | DEEP | XHIGH | EXTREME |
|-------|------|--------|------|-------|---------|
| planning_depth | 0 | 1 | 2 | 3 | 4 |
| retrieval_depth | 0 | 1 | 2 | 3 | 4 |
| evidence_threshold | low | medium | high | high | very high |
| independent_attempts | 1 | 1 | 2 | 3 | 4 |
| critique_passes | 0 | 1 | 2 | 3 | 4 |
| verification_passes | 0 | 1 | 2 | 3 | 4 |
| parallelism | off | off | off | optional | expected |

These are **workflow dials**. They do **not** map one-to-one to Qwen API
parameters; the Inference Adapter performs that mapping (see
[`inference.md`](inference.md)).

---

## 3. Profile → Policy Translation

```text
ReasoningProfile ──▶ InferencePolicy ──▶ Provider-specific parameters
```

- The **Reasoning Policy Engine** resolves a `ReasoningProfile` (plus the task's
  complexity assessment) into an **`InferencePolicy`**: a provider-neutral
  statement of *how* to call the model (temperature/top-p intent, sampling
  budget, structured-output requirements, max tokens, whether tool-calling is
  allowed, whether streaming is used).
- The **Inference Adapter** translates the `InferencePolicy` into concrete
  parameters for the selected `InferenceProvider`, using the provider's
  `capability_info()` to decide what is actually controllable.

No Qwen API parameter name appears anywhere in the reasoning engine.

---

## 4. Canonical Deep Workflow

```text
User Request
    ↓ Intent Classification
    ↓ Complexity Assessment
    ↓ Reasoning Profile Selection
    ↓ Task Decomposition
    ↓ Context Planning
    ↓ Evidence Retrieval
    ↓ Primary Reasoning
    ↓ Tool / Computation Execution
    ↓ Counterargument Generation
    ↓ Critique
    ↓ Verification
    ↓ Synthesis
    ↓ Citation / Provenance Audit
    ↓ Final Response
    ↓ Persist Research State
```

### Stage skipping / repetition

The Workflow Engine evaluates per-stage **entry conditions** against the task
complexity and the profile. For example:

- `FAST` may run only: classify → reason → respond.
- `DEEP` runs the full linear path.
- `XHIGH`/`EXTREME` may **repeat** `critique → verification → synthesis` until
  the `evidence_threshold` and `verification_passes` are satisfied, or loop
  `retrieve → reason` when verification finds gaps.

Each stage is idempotent and resumable; a stage's output is persisted so a
resumed session never re-runs completed stages.

---

## 5. Iterative Reasoning Passes

```text
Pass 1 → hypothesis
Pass 2 → evidence
Pass 3 → challenge
Pass 4 → correction
Pass 5 → verification
Pass 6 → synthesis
```

The workflow engine manages passes as a **state machine**. The persisted state
for a pass is limited to structured items:

- hypotheses
- claims
- evidence references
- decisions
- unresolved questions
- tool results
- verification outcomes
- workflow state

**Invariant:** hidden chain-of-thought is **never** stored, transmitted,
logged, or exposed by any tool or log. Only the structured *outcomes* of
reasoning are persisted. This is enforced structurally (the persistence layer
has no field for raw reasoning text) rather than by convention.

---

## 6. Task Decomposition & Planning

- **Intent Classification** — coarse routing (question, research, computation,
  retrieval, write/artifact, mixed).
- **Complexity Assessment** — a lightweight, deterministic rubric (number of
  sub-questions, need for evidence, need for computation, ambiguity) that picks
  a profile. It may be model-assisted but its output is a bounded enum.
- **Task Decomposer** — splits into `tasks` with declared dependencies and
  expected artifacts. Decomposition depth is bounded by `planning_depth`.
- **Context Planner** (in Context Engine) — decides what evidence/tools each
  task will need *before* reasoning runs.

---

## 7. Long-Output Strategy

Long outputs are a workflow capability (see [`ARCHITECTURE.md` §16](../../ARCHITECTURE.md)).
The engine supports:

```text
single response | sectioned generation | continuation
artifact-first generation | incremental synthesis | final assembly
```

Maintained state:

```text
completed_sections · remaining_sections · claims_used · citations_used
style_constraints · open_issues
```

A report that exceeds a single response limit is generated section-by-section,
with each section checked for coherence against prior sections and the
`claims_used`/`citations_used` ledger updated so the final assembly audit is
consistent.

---

## 8. Failure Modes the Design Must Handle

| Failure mode | Mitigation |
|--------------|------------|
| Model loops / repeats a stage forever | Stage repetition is budgeted by profile fields (`*_passes`, `independent_attempts`) |
| Verification finds a contradiction | Loop to `retrieve → reason` or record an `unresolved_question` and proceed explicitly |
| Task exceeds context budget | Context Engine compacts and prioritizes; never silently truncates the middle |
| Session interrupted mid-workflow | Checkpoint after every stage; resume from last completed stage |
| Profile fields unsupported by backend | Inference Adapter degrades gracefully via `capability_info()` and records the degradation |

---

## 9. Decision Record

- [0003 — Reasoning profile as policy, not prompt](decisions/0003-reasoning-profile-as-policy.md)
- [0007 — Verification as a first-class subsystem](decisions/0007-verification-first-class.md)
