# ADR 0003 — Reasoning profile as workflow/inference policy

- **Status:** Accepted
- **Amended by:** 0014, 0015

## Decision

Represent reasoning effort (FAST/NORMAL/DEEP/XHIGH/EXTREME) as a
`ReasoningProfile` — a set of workflow dials (planning_depth, retrieval_depth,
evidence_threshold, independent_attempts, critique_passes, verification_passes,
context_budget, output_budget, continuation_policy, parallelism) — and translate
it through `InferencePolicy` to provider-specific parameters. Never represent
effort as a longer system prompt.

## Reason

"XHigh" implemented as a long prompt is neither measurable, reproducible, nor
portable: it breaks when the backend changes and cannot be audited. Modeling
effort as explicit workflow behavior makes the effort level a real, observable,
resumable process that is independent of any backend's prompting quirks.

## Alternatives considered

- **Prompt templates per level:** trivial, but couples behavior to a backend and
  provides no verifiable semantics.
- **Backend "thinking"/reasoning flags only:** convenient but provider-locked
  and gives no control over retrieval/verification depth.

## Trade-offs

- Requires building the workflow/verification machinery that a prompt would
  "fake."
- Slightly more tokens/latency for low-effort tasks if the dials are
  mis-calibrated (mitigated by FAST/NORMAL shortcuts).

## Reversibility

Moderate. The `ReasoningProfile` shape may be extended (additive fields); the
prompt approach it replaces is a subset that can still be expressed by a
degenerate profile. The translation seam (ADR 0004) absorbs backend-specific
behavior.
