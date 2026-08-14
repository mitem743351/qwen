# Verification

The **verification engine** runs deterministic, config-driven procedures over a
claim, its linked evidence, source-quality assessments, and corpus facts, and
emits a scoped `VerificationReport`. Verification is **never absolute**.

Module: `python/qwen_research/verification/`.

---

## Scope & non-absolute semantics

> `VERIFIED_WITHIN_CORPUS` means *"passed the configured deterministic
> procedures against the currently indexed corpus"*, **not** "true". The word
> `VERIFIED` is never used unqualified in the codebase.

---

## Verification statuses

```text
UNREVIEWED            — no verification performed
RETRIEVED             — evidence materialized from retrieval, not yet assessed
ASSESSED              — evidence assessed, but no supporting link
PARTIALLY_SUPPORTED   — supporting link(s), but an ERROR/CRITICAL issue remains
SUPPORTED             — supporting link(s), no blocking issue, single source
CONTESTED             — contradicting evidence present
CONTRADICTED          — a CONFIRMED contradiction with another claim
INSUFFICIENT_EVIDENCE — no linked evidence at all
VERIFIED_WITHIN_CORPUS— ≥2 independent supporting sources, no blocking issue
```

These are **run-scoped**; they map back onto the claim's memory-promotion
status (`_claim_status_for`) without ever equating any of them with truth:

```text
VERIFIED_WITHIN_CORPUS → CORROBORATED
SUPPORTED / PARTIALLY_SUPPORTED → SUPPORTED
CONTESTED / CONTRADICTED → CONTESTED
ASSESSED → ASSESSED
everything else → UNREVIEWED
```

---

## Deterministic rules

`VerificationFacts` bundles the assembled facts; ten pure rules run over them:

| Rule | Finding | Severity |
|------|---------|----------|
| `claim_has_no_evidence` | claim has no linked evidence | WARNING |
| `evidence_source_missing` | evidence source not in corpus | ERROR |
| `evidence_chunk_missing` | evidence chunk no longer in index | ERROR |
| `evidence_excerpt_empty` | evidence excerpt is empty | ERROR |
| `source_provenance_incomplete` | source provenance incomplete | WARNING |
| `duplicate_evidence` | duplicate evidence link for the claim | INFO |
| `no_independent_corroboration` | single source (no independent corroboration) | INFO |
| `support_contradiction_conflict` | both supporting and contradicting evidence | ERROR |
| `stale_document` | evidence from a stale document | ERROR |
| `unextractable_source` | source extraction quality unextractable/OCR-required | WARNING |

Each rule is pure and deterministic; none invokes a model.

---

## Status derivation

`_derive_status` resolves the report status from links, contradictions, issues,
and the independent-source count:

1. no links → `INSUFFICIENT_EVIDENCE`
2. a `CONFIRMED` contradiction → `CONTRADICTED`
3. any `CONTRADICTS` link → `CONTESTED`
4. no `SUPPORTS` link → `ASSESSED`
5. ≥2 independent sources and no ERROR/CRITICAL issue → `VERIFIED_WITHIN_CORPUS`
6. an ERROR/CRITICAL issue → `PARTIALLY_SUPPORTED`
7. otherwise → `SUPPORTED`

---

## Corroboration (source/document level)

Corroboration counts **independent sources**, not chunks: ten chunks from one
paper are one source. Independence is a heuristic over available metadata
(see [`evidence-integrity.md`](evidence-integrity.md) and
`qwen_research/sources/independence.py`):

```text
INDEPENDENT · DEPENDENT · UNKNOWN
```

- same document / same source / same publisher → `DEPENDENT`
- distinct document **and** distinct source → `INDEPENDENT` (even under one
  corpus root — the normal "two papers in one corpus" case)
- same corpus root with undecidable identity (weak signal) → `UNKNOWN`
- otherwise → `UNKNOWN`

The engine derives a `SourceIdentity` per supporting evidence item (document,
source, publisher, corpus root) and runs `count_independent_sources`, which
collapses items joined by a `DEPENDENT` relationship (transitively) and counts
the remaining groups. Corroboration therefore respects same-publisher and
same-document ties, not merely distinct document ids; `no_independent_corroboration`
fires below 2.

---

## Verification coverage

`Coverage` records deterministic coverage metrics — never a truth probability:

```text
claims_checked
claims_with_evidence
claims_with_independent_corroboration
claims_with_contradictions
claims_with_unresolved_issues
```

---

## Report

```text
VerificationReport
    report_id · scope (VerificationScope) · claim_id · project_id
    status · issues (tuple[VerificationIssue, ...])
    evidence · contradictions · source_assessments  (tuple of ids)
    coverage · generated_at
```

`VerificationScope`: `SOURCE · EVIDENCE · CLAIM · RESEARCH_STATE · PROJECT`
(Phase 5 exercises `CLAIM`). `VerificationIssue` carries `code`, `severity`
(`INFO/WARNING/ERROR/CRITICAL`), `entity_type`, `entity_id`, and `message`.

---

## Engine & service

- `VerificationEngine` (provider-independent): fact assembly
  (`materialize_evidence`, source-quality caching, stale-document lookup),
  rule execution, status derivation, report construction. Accepts an optional
  `CorpusIndex`; when absent, evidence/source checks degrade to empty (no
  fabrication).
- `EvidenceIntegrityService` (application façade used by the Research Runtime):
  `create_claim`, `get_claim`, `link_claim_evidence`, `assess_evidence`,
  `verify_claim`, `get_verification_report`, `get_contradictions`. It
  materializes evidence, validates references atomically, detects project
  contradictions, persists reports, and updates claim status.
- `VerificationAssistant` protocol is the seam for a future model-assisted
  layer; Phase 5 ships `NoOpVerificationAssistant` (returns
  `UNKNOWN` / `insufficient_information`).

---

## Evidence assessment

`assess_evidence` produces an `EvidenceAssessment`:

```text
assessment_id · claim_id · evidence_id
support_type   SupportType (see evidence model)
rationale · status · quality (EvidenceQuality)
```

`SupportType` is `DIRECT_SUPPORT · INDIRECT_SUPPORT · CONTEXT ·
QUALIFICATION · CONTRADICTION · NON_SUPPORT · UNKNOWN`, mapped from the
claim–evidence relationship — never from retrieval score.

---

## Source quality

`SourceQualityAssessor.assess(media_type, metadata)` is deterministic and
config-driven (no LLM judge, no web scraping). Tiers:

```text
TIER_1 primary/official/standard/original result
TIER_2 peer-reviewed secondary research
TIER_3 reputable technical/institutional source
TIER_4 secondary web source / reporting
TIER_5 unverified / low-provenance (default)
```

A tier reflects source **characteristics**, not correctness. Source quality is
independent of retrieval relevance and is cached per source id in the store.

See [`evidence-integrity.md`](evidence-integrity.md),
[`claims.md`](claims.md), and [`contradictions.md`](contradictions.md).
