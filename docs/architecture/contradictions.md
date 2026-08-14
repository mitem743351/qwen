# Contradictions

A **contradiction** is a first-class entity between two claims, carrying
evidence references, a type, a severity, a status, and a rationale. Phase 5
performs **structural, deterministic** comparison over structured claim
metadata only — no natural-language contradiction detection, no LLM reasoning.

Module: `python/qwen_research/contradictions/`.

---

## Types

```text
DIRECT_CONTRADICTION    — mutually exclusive values within overlapping scope
CONTEXTUAL_CONTRADICTION— conflict explained by context (candidate, not emitted)
TEMPORAL_CONTRADICTION  — conflict explained by non-overlapping time ranges
DEFINITIONAL_CONFLICT   — different metrics or units (not a contradiction)
METHODOLOGICAL_CONFLICT — values conflict but methods differ
SCOPE_CONFLICT          — conflict explained by differing scope
APPARENT_CONTRADICTION  — values are compatible (not a contradiction)
UNKNOWN                 — insufficient information to determine
```

## Statuses

```text
CONFIRMED                — mutually exclusive within overlapping scope
POSSIBLE                 — values conflict but scope unconstrained / methods differ
NOT_A_CONTRADICTION      — resolved by scope/temporal/definitional distinction
INSUFFICIENT_INFORMATION — no structured metadata to compare
```

**Not every disagreement is `CONFIRMED`.** A disagreement that is explained by
time, scope, method, or definition is *not* a contradiction.

## Severity

`INFO · WARNING · ERROR · CRITICAL` — `CONFIRMED → ERROR`, `POSSIBLE → WARNING`,
other → `INFO`. Severity is a verification concern, **not** falsehood.

---

## Deterministic assessment

`assess_contradiction(claim_a, claim_b)` requires both claims to carry
`QuantitativeClaim` metadata; otherwise it returns `INSUFFICIENT_INFORMATION`.
The decision order is:

1. different `metric` → `DEFINITIONAL_CONFLICT`, `NOT_A_CONTRADICTION`
2. different `unit` (both set) → `DEFINITIONAL_CONFLICT`, `NOT_A_CONTRADICTION`
3. `_values_incompatible(value_a, op_a, value_b, op_b)` decides mutual
   exclusivity (e.g. `= x` vs `= y` with `x ≠ y`; `< x` vs `>= y` with `y ≥ x`).
   Compatible → `APPARENT_CONTRADICTION`, `NOT_A_CONTRADICTION`.
4. values incompatible: check **temporal** ranges (extracted 4-digit years) —
   non-overlapping → `TEMPORAL_CONTRADICTION`, `NOT_A_CONTRADICTION`.
5. then **scope** — differing `population`/`region`/`dataset` →
   `SCOPE_CONFLICT`, `NOT_A_CONTRADICTION`; differing `method` →
   `METHODOLOGICAL_CONFLICT`, `POSSIBLE`.
6. no scope on either side → `DIRECT_CONTRADICTION`, `POSSIBLE`.
7. scopes overlap → `DIRECT_CONTRADICTION`, `CONFIRMED`.

---

## Detection

`detect_contradiction(claim_a, claim_b)` returns a `Contradiction` entity only
for `CONFIRMED` or `POSSIBLE` assessments; resolved disagreements yield `None`.
`detect_contradictions(claims)` compares all pairs within a project.

Contradictions are persisted and deduplicated by claim pair
(`_pair_key` sorts the pair), so re-verification does not duplicate entities.
A claim's contradictions are surfaced in its verification report and drive the
`CONTRADICTED` status.

---

## Model

```text
Contradiction
    contradiction_id · project_id
    claim_a · claim_b   (ClaimId)
    evidence_a · evidence_b (str | None)
    type · severity · status · rationale
    created_at · updated_at
```

See [`verification.md`](verification.md) and
[`evidence-integrity.md`](evidence-integrity.md).
