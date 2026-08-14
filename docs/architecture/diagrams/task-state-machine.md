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

    RETRIEVING --> NEEDS_INPUT
    REASONING --> NEEDS_INPUT
    VERIFYING --> RETRIEVING : evidence gap
    EXECUTING --> REASONING : retry

    CREATED --> CANCELLED
    CLASSIFIED --> CANCELLED
    PLANNED --> CANCELLED
    RETRIEVING --> CANCELLED
    REASONING --> CANCELLED
    EXECUTING --> CANCELLED
    VERIFYING --> CANCELLED
    SYNTHESIZING --> CANCELLED

    RETRIEVING --> FAILED
    REASONING --> FAILED
    EXECUTING --> FAILED
    VERIFYING --> FAILED

    state WAITING {
        [*] --> PAUSED
        PAUSED --> [*]
    }
    REASONING --> WAITING
    EXECUTING --> WAITING
    WAITING --> REASONING : resume
```

**Notes**

- A task is **resumable** at any state boundary.
- Workflow state is **never encoded only in memory** — the architecture assumes
  persistence will eventually exist (see
  [`domain-contracts.md`](../domain-contracts.md#7-task-state-machine)).
- `VERIFYING → RETRIEVING` is the verification-driven loop (evidence gap).
