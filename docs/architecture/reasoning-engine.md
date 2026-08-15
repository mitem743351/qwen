# Reasoning Engine

The reasoning architecture: profiles, the policy translation, the workflow
engine, iterative passes, and the rules that keep reasoning auditable without
exposing hidden chain-of-thought.

---

## 1. Core Principle

**Reasoning is an explicit policy system, not a prompt-writing exercise.**

`XHIGH` is not a longer system prompt. It is a named `ReasoningProfile` that the
Workflow Engine (Research Runtime) and the Inference Runtime jointly enact. The
same profile produces consistent *behavior* regardless of which backend is
underneath.

> **Ownership caveat.** A `ReasoningProfile` is an abstract resource-allocation
> and workflow policy. It does **not** guarantee a specific model reasoning
> budget unless the active inference owner/provider exposes the required
> controls. In `STUDIO_NATIVE` mode the workflow engine can only *influence*
> the model through tool outputs and structured capabilities; it cannot
> directly set thinking budget, temperature, `top_p`, or max generation tokens.

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
parameters; the Inference Runtime performs that mapping through explicit
**capability negotiation** (see [`capability-negotiation.md`](capability-negotiation.md)).

---

## 2a. ReasoningBudget (resource profile)

Every `ReasoningProfile` implies a `ReasoningBudget` — the resource-allocation
facet of the profile:

```text
ReasoningBudget
    inference_budget       # total inference passes/tokens
    retrieval_budget       # corpus queries / evidence items
    tool_budget            # tool call count/cost
    context_budget         # model context allocation
    verification_budget    # verification passes
    output_budget          # response/report length
    time_budget            # wall-clock ceiling
    parallelism_budget     # concurrent trajectories
```

`XHIGH` and `EXTREME` are **resource profiles** — larger allocations across
these dimensions — not merely "more prompt." The scheduler may later allocate
these dynamically; adaptive scheduling is not implemented in this phase.

### What XHIGH/EXTREME mean per mode

```text
XHIGH / EXTREME
├── deeper planning
├── more retrieval
├── more evidence
├── more critique
├── more verification
├── more context
├── more output budget
└── more inference passes  ← only when gateway-owned inference is available
```

- **GATEWAY_INFERENCE:** all of the above, including actual provider-specific
  inference parameters where the provider supports them.
- **STUDIO_NATIVE:** XHIGH/EXTREME translate primarily into richer tool usage,
  better retrieval, stronger evidence, verification tools, and structured
  workflow — **not** direct control over hidden model thinking tokens.

### Native vs workflow-emulated effort (Phase 1.2)

`XHIGH` requests *high reasoning effort*, *a reasoning budget*, *parallel
trajectories*, and *long output* — but negotiation separates **native provider
capabilities** from **external workflow capabilities**. For example, against a
provider with native tool-calling but *no* reasoning budget and *no* parallel
generation:

```text
tool calling       → APPLY   (native)
reasoning budget   → EMULATE (workflow passes)
parallel generation → EMULATE (sequential trajectories)
```

An emulated capability is a workflow directive, never a provider parameter:
`ReasoningProfile.inference_policy()` expresses the *intent*; capability
negotiation resolves it to native support or an external emulation strategy.
The eventual workflow engine executes the emulation strategies.

---

## 3. Profile → Policy Translation

```text
ReasoningProfile ──▶ InferencePolicy ──▶ Capability negotiation ──▶ Provider-specific parameters
```

- The **Reasoning Policy Engine** resolves a `ReasoningProfile` (plus the task's
  complexity assessment) into an **`InferencePolicy`**: a provider-neutral
  statement of *how* to call the model, expressed as capability-aligned intents
  (`reasoning`, `reasoning_budget`, `max_output_tokens`, `temperature`, `top_p`,
  `preserved_thinking`, `tool_calling`, `structured_output`, `streaming`,
  `parallel_generation`, `context_caching`) plus the single authoritative
  `model_requirement` (Phase 1.1).
- The **capability-negotiation layer** (in the Inference Runtime) intersects the
  `InferencePolicy` with the provider's `capabilities()` and assigns each
  element an outcome — `APPLY` / `DEGRADE` / `EMULATE` / `REJECT` (see
  [`capability-negotiation.md`](capability-negotiation.md)).
- The **Inference Runtime** then emits concrete provider-specific parameters.

No Qwen API parameter name appears anywhere in the reasoning engine. In
`STUDIO_NATIVE` mode this translation is **not performed at all** — the local
system has no inference ownership.

---

## 4. Canonical Deep Workflow

This workflow **runs under the Workflow Engine only when the system owns
inference** (`GATEWAY_INFERENCE`, or escalated `HYBRID` tasks). In
`STUDIO_NATIVE` mode the same stages exist as *tools the model may invoke*, but
the model (Qwen Studio) retains control of the overall loop.

### Workflow Engine boundary

The Workflow Engine belongs to the **Research Runtime**. It decides *which
stage runs, what comes next, when to retry/continue, when verification is
required, and when completion criteria are met* — but it never constructs
provider-specific HTTP requests:

```text
Workflow Engine → Inference Runtime → Provider
```

This prevents Qwen API details from leaking into workflow definitions.

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

> **`workflow state ≠ hidden model chain-of-thought`.** The structured state
> above (`task`, `plan`, `hypotheses`, `claims`, `evidence references`, `tool
> results`, `decisions`, `unresolved questions`, `verification results`,
> `section state`, `artifact state`) is *our* orchestration record, and it is
> equally useful in `STUDIO_NATIVE` and `GATEWAY_INFERENCE` modes. It contains
> nothing the model "thought" internally.

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

> **Generation limit ≠ document length.** MCP does not bypass Qwen Studio's
> generation limits. Long-output *as a Research-Runtime-owned workflow*
> (sectioned generation, continuation, state persistence, incremental
> synthesis, artifact assembly) is available in `GATEWAY_INFERENCE` mode. In
> `STUDIO_NATIVE` mode long output is **client-dependent** — the system can
> persist partial sections and artifacts but cannot extend the host model's own
> response length.

---

## 8. Failure Modes the Design Must Handle

| Failure mode | Mitigation |
|--------------|------------|
| Model loops / repeats a stage forever | Stage repetition is budgeted by profile fields (`*_passes`, `independent_attempts`) |
| Verification finds a contradiction | Loop to `retrieve → reason` or record an `unresolved_question` and proceed explicitly |
| Task exceeds context budget | Context Engine compacts and prioritizes; never silently truncates the middle |
| Session interrupted mid-workflow | Checkpoint after every stage; resume from last completed stage |
| Profile fields unsupported by backend | Capability negotiation assigns `DEGRADE`/`EMULATE`/`REJECT` and records the outcome |
| Backend lacks reasoning-budget control | XHIGH degrades to workflow-only depth (more retrieval/verification); never silently claimed |
| Studio-native mode asked to "increase thinking" | Explicitly unsupported; system refuses to claim inference control it does not have |

---

## 9. Decision Record

- [0003 — Reasoning profile as policy, not prompt](decisions/0003-reasoning-profile-as-policy.md)
- [0007 — Verification as a first-class subsystem](decisions/0007-verification-first-class.md)

## Phase 7 — orchestration consumption

Phase 7 actually **consumes** the profiles: the `ResearchPlanner` derives
workflow-level resource behavior (retrieval/verification/computation budgets,
parallelism) from `FAST`/`NORMAL`/`DEEP`/`XHIGH`/`EXTREME`, bounded by
`ReasoningBudget`. See [`orchestration.md`](orchestration.md) and
[`planning.md`](planning.md).
