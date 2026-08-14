# Architectural Decision Records (ADRs)

Each record documents a major architectural decision with: **Decision, Reason,
Alternatives considered, Trade-offs, Reversibility.**

| # | Title | Status |
|---|-------|--------|
| 0001 | Five-layer separation of concerns | Accepted |
| 0002 | Polyglot boundaries (Python/Rust/TS/SQL/Shell) | Accepted |
| 0003 | Reasoning profile as workflow/inference policy, not a prompt | Accepted |
| 0004 | Provider-independent inference abstraction | Accepted |
| 0005 | Retrieval as a pipeline, separated from reasoning | Accepted |
| 0006 | Differentiated memory stores | Accepted |
| 0007 | Verification as a first-class, independently callable subsystem | Accepted |
| 0008 | Deterministic computation separated from model reasoning | Accepted |
| 0009 | Small semantic MCP surface with class-based permissions | Accepted |
| 0010 | Dedicated Context Engine (no string-concatenation context) | Accepted |
| 0011 | Local-first, in-process orchestration (no microservices) | Accepted |
| 0012 | Artifacts as first-class, provenance-tracked objects | Accepted |
| 0013 | Least-privilege security model | Accepted |

New ADRs are appended with the next number and a status (`Proposed` →
`Accepted` / `Superseded by NNNN`).
