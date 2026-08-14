# Task State Machine

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> CLASSIFIED
    CLASSIFIED --> PLANNED
    PLANNED --> RETRIEVING
    RETRIEVING --> REASONING
    REASONING --> EXECUTING
    EXECUTING --> VERIFYING
    VERIFYING --> SYNTHESIZING
    SYNTHESIZING --> COMPLETED
    COMPLETED --> [*]

    VERIFYING --> RETRIEVING : evidence gap
    EXECUTING --> REASONING : retry

    RETRIEVING --> NEEDS_INPUT
    REASONING --> NEEDS_INPUT
    NEEDS_INPUT --> RETRIEVING
    NEEDS_INPUT --> REASONING

    REASONING --> PAUSED
    EXECUTING --> PAUSED
    PAUSED --> REASONING
    PAUSED --> EXECUTING

    REASONING --> WAITING
    EXECUTING --> WAITING
    WAITING --> REASONING
    WAITING --> EXECUTING

    RETRIEVING --> FAILED
    REASONING --> FAILED
    EXECUTING --> FAILED
    VERIFYING --> FAILED

    CREATED --> CANCELLED
    CLASSIFIED --> CANCELLED
    PLANNED --> CANCELLED
    RETRIEVING --> CANCELLED
    REASONING --> CANCELLED
    EXECUTING --> CANCELLED
    VERIFYING --> CANCELLED
    SYNTHESIZING --> CANCELLED
    NEEDS_INPUT --> CANCELLED
    PAUSED --> CANCELLED
    WAITING --> CANCELLED
```

**Notes**

- **Execution states** (the linear progression plus `FAILED`/`CANCELLED`):
  `CREATED → CLASSIFIED → PLANNED → RETRIEVING → REASONING → EXECUTING →
  VERIFYING → SYNTHESIZING → COMPLETED`.
- **Control/suspension states**: `PAUSED`, `WAITING`, `NEEDS_INPUT` — valid
  *domain* states, but the runtime does not yet operate a pause/resume engine
  (reserved in Phase 1.1).
- **Terminal states**: `COMPLETED`, `FAILED`, `CANCELLED` — no outgoing
  transitions. `NEEDS_INPUT` (and the other control states) are non-terminal.
- `VERIFYING → RETRIEVING` is the verification-driven loop (evidence gap);
  `EXECUTING → REASONING` is the retry loop.
- A task is **resumable** at any state boundary; workflow state is never
  encoded only in memory.
