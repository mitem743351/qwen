# Evidence Integrity & Verification Foundation

Phase 5 establishes the **evidence-integrity foundation**: a structured claim
model, a persistent evidence model, source-quality assessment, claim–evidence
relationships, corroboration, contradiction analysis, and a deterministic
verification engine. It is the deterministic baseline that later phases will
extend — **no model reasoning, no web fact-checking, no LLM judge**.

---

## Why this exists

Retrieval returns *candidates*. It does not tell you whether a claim is
supported. Phase 5 makes the following distinct, so none of them collapse into
each other:

| Layer | Question it answers | Produced by |
|-------|---------------------|-------------|
| **Retrieval** | "Was this chunk returned for this query?" | `Retriever` (FTS5 / embedding / hybrid) |
| **Evidence** | "Which evaluated units bear on this claim, and how?" | `EvidenceRecord` + `ClaimEvidenceLink` |
| **Source quality** | "What kind of source is this, and how complete is its provenance?" | `SourceQualityAssessor` |
| **Corroboration** | "Do ≥2 *independent* sources support this?" | `VerificationEngine` (independence heuristic) |
| **Verification** | "Does this claim pass the configured deterministic procedures against the current corpus?" | `VerificationReport` |

A claim may be *retrieved* without being *relevant*, *relevant* without
*supporting*, *supported by one source* without being *corroborated*,
*corroborated* without being *true*, and *contested* by another source without
being *refuted*. Each is a distinct determination with its own mechanism.

---

## Non-truth semantics (binding)

The verification vocabulary is deliberately bounded. The system **never**
outputs `TRUE`, `FACT`, `PROVEN`, or `CERTAIN`. The strongest available status
is:

> **`VERIFIED_WITHIN_CORPUS`** — *"passed the configured deterministic
> procedures against the currently indexed corpus."* It is **not** absolute
> truth.

The canonical distinctions, stated once and used everywhere:

- `source ≠ evidence` — a source is where text comes from; evidence is the
  evaluated unit that bears on a claim.
- `evidence ≠ claim` — evidence is a retrieved/excerpted unit; a claim is an
  assertable statement.
- `claim ≠ conclusion` — a claim is a reviewable proposition; a conclusion is
  the product of synthesis (not part of Phase 5).
- `retrieval relevance ≠ source quality ≠ evidence strength ≠ claim confidence
  ≠ truth` — five different axes, five different computations.
- `SUPPORTED ≠ CORROBORATED ≠ TRUE` — single-source support, multi-source
  independent support, and truth are different things.
- `UNREVIEWED` claims are **never silently promoted** to durable knowledge.

---

## End-to-end path

```text
User: "Is claim X supported by my research corpus?"
  → Qwen Studio
  → MCP (create_claim / link_claim_evidence / assess_evidence / verify_claim)
  → Research Runtime
  → Retrieval + Memory → Evidence + prior claims
  → Verification Engine
  → sources + claims + contradictions
  → Verification Report
  → bounded ResearchContext
  → Qwen Studio
```

The verification engine assembles **facts** (claim, linked evidence, source
quality, chunk status, independence count) and runs **deterministic rules** to
emit a scoped `VerificationReport`. It never calls a model.

All claim operations are **project-scoped**: lookup, link, assessment,
verification, and report reads take a `project_id`, and a claim/report id from
one project never resolves from another. Claim `source_refs` are validated
against the corpus at creation. Bounded `VerificationSummary` objects (one per
verified claim) flow into the `ResearchContext` so the model sees *how* prior
claims were verified without the full issue lists.

---

## Packages (all under `python/qwen_research/`)

| Package | Responsibility |
|---------|----------------|
| `claims/` | `Claim`, `ClaimStatus`, `ClaimType`, `Scope`, `QuantitativeClaim`, `ClaimEvidenceLink` |
| `evidence/` | `EvidenceRecord`, `SupportType`, `ExtractionQuality`, `EvidenceQuality` |
| `sources/` | `SourceTier`, `SourceQuality`, `SourceQualityAssessor`, `SourceIdentity`, `assess_independence`, `count_independent_sources` |
| `contradictions/` | `Contradiction`, types/statuses/severities, `assess_contradiction`, `detect_contradiction(s)` |
| `verification/` | `VerificationEngine`, rules, statuses, `Coverage`, `EvidenceAssessment`, `VerificationReport`, `EvidenceIntegrityService`, `SqliteVerificationStore` |

Dependencies flow downward: `common ← domain ← {claims, evidence, sources,
contradictions} ← verification ← research ← mcp`. None of these packages import
MCP, Qwen-API, HTTP, or LLM/embedding libraries.

---

## Persistence

`SqliteVerificationStore` (`QWEN_RESEARCH_VERIFICATION_DB`) holds claims,
claim–evidence links, evidence assessments, contradictions, verification
reports, and source-quality records in one local SQLite database
(`schema_version = 1`, WAL, thread-local connections, write lock). All writes
are transactional and provenance-validated: a failed reference resolution
(e.g. a claim or evidence id that does not exist) raises a typed error and
**nothing is persisted**.

---

## What is deliberately **not** in Phase 5

- No Qwen API / gateway inference, no LLM claim extraction, no LLM
  contradiction reasoning, no LLM source-quality judgment.
- No web fact-checking, no multi-agent verification, no adversarial debate.
- No `sentence-transformers` / `fastembed` / `transformers` / CUDA / GPU.
- No vector/ANN backends (FAISS/Qdrant/Milvus/Weaviate/sqlite-vec).
- No OCR, Office parsing, computer use, remote MCP, dashboard, Rust
  acceleration.

The `VerificationAssistant` protocol exists as a **seam** for a future
model-assisted layer; Phase 5 ships only `NoOpVerificationAssistant`.

See [`claims.md`](claims.md), [`verification.md`](verification.md),
[`contradictions.md`](contradictions.md), and
[`../setup/verification.md`](../setup/verification.md).
