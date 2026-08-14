# Memory Model

```mermaid
erDiagram
    PROJECT ||--o{ SESSION : "contains"
    PROJECT ||--o{ DOCUMENT : "scopes"
    PROJECT ||--o{ QUESTION : "owns"
    SESSION ||--o{ TASK : "runs"
    SESSION ||--o{ DECISION : "records"
    SESSION ||--o{ ARTIFACT : "produces"
    TASK ||--o{ CLAIM : "asserts"
    TASK ||--o{ ARTIFACT : "produces"
    DOCUMENT ||--o{ SOURCE : "cites"
    DOCUMENT ||--o{ SOURCE : "derived_from"
    SOURCE ||--o{ CLAIM : "supports"
    CLAIM }o--o{ EVIDENCE : "backed_by"
    CLAIM }o--o{ ENTITY : "involves"
    EVIDENCE }o--|| SOURCE : "located_in"
    QUESTION ||--o{ CLAIM : "addressed_by"
    DECISION ||--o{ QUESTION : "resolves"

    PROJECT {
        string project_id PK
        string name
        string scope
    }
    SESSION {
        string session_id PK
        string project_id FK
        string state
        string checkpoint
    }
    DOCUMENT {
        string document_id PK
        string source_hash
        string state
    }
    SOURCE {
        string source_id PK
        string document_id FK
        string locator
        string kind
    }
    CLAIM {
        string claim_id PK
        string text
        string status
        string source_hash
    }
    EVIDENCE {
        string evidence_id PK
        string source_id FK
        string span
        float score
        string citation
    }
    ENTITY {
        string entity_id PK
        string name
        string type
    }
    QUESTION {
        string question_id PK
        string status
    }
    DECISION {
        string decision_id PK
        string rationale
        datetime created_at
    }
    ARTIFACT {
        string artifact_id PK
        string type
        string path
        int version
        string generation_metadata
    }
```

**Notes**

- Six differentiated stores map onto these entities: Session Memory (session,
  task), Project Memory (project, document, source), Research Memory
  (cross-project claims/evidence), Knowledge Base (entity, relations),
  Unresolved Questions (question), Decision History (decision).
- `DECISION` is append-only.
- `DOCUMENT.state` enforces the RAW→INDEXED→STRUCTURED→DERIVED progression;
  RAW is never mutated.
- `CLAIM.source_hash` links claims to the immutable source version that
  supported them, enabling re-verification when a source changes.
