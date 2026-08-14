# ADR 0005 — Retrieval as a pipeline, separated from reasoning

- **Status:** Accepted

## Decision

Implement retrieval as a self-contained pipeline (normalize → candidate
retrieval {lexical|semantic|metadata} → hybrid ranking → reranking → evidence
extraction → citation resolution → context assembly) that is fully decoupled
from reasoning. Defer the embedding model and vector store behind `Embedder` and
`VectorIndex` interfaces.

## Reason

Retrieval and reasoning fail for different reasons and must be independently
testable and replaceable. Keeping retrieval out of reasoning also prevents the
retriever from silently filtering disconfirming evidence, and lets verification
run independent searches. Deferring the vector choice avoids premature
commitment while the corpus is still small.

## Alternatives considered

- **Retrieval inside the model (model reads docs directly):** simplest, but
  hides indexing behind prompts, breaks provenance, and bloats context.
- **Single monolithic index (no hybrid):** simpler, but fragile to vocabulary
  gaps and metadata-only queries.

## Trade-offs

- More stages and moving parts than a single index.
- The `Embedder`/`VectorIndex` abstraction adds indirection now to avoid
  rework later.

## Reversibility

High. Each stage is an independent component; the vector backend decision is
explicitly deferred and swappable, and a pure-lexical v1 is a valid early
implementation.
