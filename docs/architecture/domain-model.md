# Domain Model

The stable, transport- and provider-independent domain objects implemented in
`python/qwen_research/domain/` and shared primitives in `common/`.

---

## Design principles

- Explicit typed dataclasses, enums, and protocols.
- Immutable / value-like where appropriate (`frozen=True`); transitions return
  new instances.
- No MCP schemas, Qwen API schemas, ORM models, or HTTP request models.
- No hidden chain-of-thought field anywhere.
- Stable, deterministic, version-aware serialization.

---

## Entities

| Entity | Module | Key fields |
|--------|--------|------------|
| `Task` | `domain/task.py` | task_id, description, session_id, status, reasoning_profile, created_at, updated_at, parent_task_id, metadata |
| `Session` | `domain/session.py` | session_id, project_id, created_at, updated_at, mode, metadata |
| `ResearchState` | `domain/research.py` | task_id, current_stage, plan, hypotheses, claims, evidence_refs, decisions, unresolved_questions, artifact_refs, verification_refs, continuation_state |
| `Source` | `domain/source.py` | source_id, uri, title, source_type, author, publication_date, metadata, content_hash |
| `Evidence` | `domain/evidence.py` | evidence_id, source_id, location, excerpt, relevance, metadata |
| `Claim` | `domain/claim.py` | claim_id, text, source_refs, evidence_refs, status, confidence, counterevidence_refs |
| `Artifact` | `domain/artifact.py` | artifact_id, artifact_type, path, task_id, session_id, created_at, provenance, version |
| `Workflow` | `domain/workflow.py` | workflow_id, name, version, configuration (descriptor) |
| `VerificationResult` | `domain/verification.py` | verification_id, claim_id, status, findings, created_at |

Auxiliary value objects: `Hypothesis`, `Decision`, `UnresolvedQuestion`,
`ResearchPlan` (in `research.py`).

---

## Reasoning

- `ReasoningProfile` (in `reasoning.py`) — an abstract workflow/resource policy,
  **not** provider parameters. Built-in presets: `FAST`, `NORMAL`, `DEEP`,
  `XHIGH`, `EXTREME`.
- `ReasoningBudget` — the resource-allocation facet (`inference_budget`,
  `retrieval_budget`, `tool_budget`, `context_budget`, `verification_budget`,
  `output_budget`, `time_budget`, `parallelism_budget`). A data object only;
  budgets are not enforced in Phase 1.

Profiles do **not** claim to control Qwen Studio's hidden reasoning; they are
workflow dials (Phase 0.5).

---

## Inference (contracts)

- `InferencePolicy`, `InferenceRequest`, `InferenceResult`, `ModelInfo`,
  `ProviderCapabilities`, `NegotiationDecision` (in `inference.py`).
- `NegotiationOutcome`: `APPLY`, `DEGRADE`, `EMULATE`, `REJECT`.
- `negotiate(policy, capabilities)` intersects policy with capabilities,
  returning an applied policy plus an explicit decision record — unsupported
  capabilities never disappear silently.

---

## State machine

`TaskStatus` (14 states): `CREATED → CLASSIFIED → PLANNED → RETRIEVING →
REASONING → EXECUTING → VERIFYING → SYNTHESIZING → COMPLETED`, plus `PAUSED`,
`WAITING`, `FAILED`, `CANCELLED`, `NEEDS_INPUT`.

`validate_transition()` rejects illegal transitions with
`InvalidTransitionError`. Terminal states (`COMPLETED`, `FAILED`, `CANCELLED`)
admit no outgoing transitions. `VERIFYING → RETRIEVING` (evidence gap) and
`EXECUTING → REASONING` (retry) are supported loops.

---

## Errors

Typed hierarchy in `domain/errors.py`: `DomainError` base; `ValidationError`,
`InvalidTransitionError`, `CapabilityError`, `UnsupportedOperationError`,
`ToolError`, `WorkflowError`, `InferenceError`, `PermissionError`,
`PersistenceError`, `ConfigurationError`. Each carries a machine-readable
`category`.

---

## Serialization

`common/serialization.py` provides `dumps`/`loads` (deterministic, version-aware
`schema_version = 1`, type-registered via `@serializable`). `from_jsonable`
reconstructs enums, datetimes, nested dataclasses, `Optional`, lists, tuples,
and dicts from type hints.

---

## Identifiers and timestamps

- `common/ids.py` — `NewType`-wrapped identifiers (`TaskId`, `SessionId`, …)
  minted by `new_id(prefix)`.
- `common/timestamps.py` — timezone-aware UTC datetimes (`utc_now()`).
