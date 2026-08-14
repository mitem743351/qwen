# Claims

A **claim** is a first-class, persistent, assertable statement with project
scoping, a typed classification, an auditable status lifecycle, and explicit
provenance. Claims are created in a reviewable `UNREVIEWED` state; the system
never auto-asserts truth. No hidden reasoning is stored on a claim.

Module: `python/qwen_research/claims/`.

---

## Claim model

```text
Claim
    claim_id            ClaimId          (minted by new_id("claim"))
    project_id          str
    text                str
    type                ClaimType
    status              ClaimStatus
    confidence          float | None     (never fabricated in Phase 5)
    source_refs         tuple[str, ...]
    evidence_refs       tuple[str, ...]
    supporting_refs     tuple[str, ...]
    contradicting_refs  tuple[str, ...]
    scope               Scope | None
    quantitative        QuantitativeClaim | None
    created_at / updated_at / version
```

`Claim.create(...)` defaults `status = UNREVIEWED`, `version = 1`,
`confidence = None`. `with_status(status)` returns a **new** instance with
`version + 1` and a bumped `updated_at` (immutable transitions).

### ClaimType

`FACTUAL · CAUSAL · COMPARATIVE · QUANTITATIVE · DEFINITIONAL · PREDICTIVE ·
METHODOLOGICAL · NORMATIVE · UNKNOWN` (`UNKNOWN` is the default when
classification is unavailable).

### ClaimStatus (memory-promotion lifecycle)

`UNREVIEWED · ASSESSED · SUPPORTED · CORROBORATED · CONTESTED · REJECTED ·
ARCHIVED`.

This is the **durable-knowledge promotion ladder**, distinct from the
verification status of a single run (see
[`verification.md`](verification.md)). `SUPPORTED ≠ CORROBORATED ≠ TRUE`.
`UNREVIEWED` claims are never silently promoted.

| Status | Meaning |
|--------|---------|
| `UNREVIEWED` | created but not yet evaluated |
| `ASSESSED` | evidence assessed, but no supporting link |
| `SUPPORTED` | at least one supporting link (single source) |
| `CORROBORATED` | ≥2 independent supporting sources |
| `CONTESTED` | contradicting evidence or a confirmed contradiction |
| `REJECTED` | explicitly rejected (not auto-assigned in Phase 5) |
| `ARCHIVED` | superseded / retired (not auto-assigned in Phase 5) |

---

## Scope

`Scope` is a lightweight structured object so two claims are **not** treated as
contradictory merely because their values differ. All fields optional:

```text
population · conditions · region · dataset · method · time_range
```

---

## Quantitative claims

`QuantitativeClaim` carries structured metadata for deterministic comparison:

```text
metric · value (float|None) · unit · operator · comparison ·
population · time_range
```

`operator` is one of `<`, `<=`, `>`, `>=`, `=`, `!=`.

---

## Claim–evidence relationships

A link is a first-class entity carrying the **semantic** meaning of "this
evidence bears on this claim" — never a bare reference list.

```text
ClaimEvidenceLink
    link_id · claim_id · evidence_id
    relationship  ClaimEvidenceRelationship
    rationale     str
    status        LinkStatus (ACTIVE | SUPERSEDED)
    created_at
```

`ClaimEvidenceRelationship`: `SUPPORTS · CONTRADICTS · QUALIFIES ·
CONTEXTUALIZES · DOES_NOT_ADDRESS`.

The relationship is **evaluative** (set by the caller / assessment), never
derived from a retrieval score.

---

## Project isolation

Claims are listed per project (`get_claims(project_id)`); claim ids are unique
so a cross-project lookup by id still resolves, but enumeration is
project-scoped. Isolation is enforced at the repository/query boundary —
never by prompts.
