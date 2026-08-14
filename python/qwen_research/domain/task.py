"""The Task domain object and its state machine."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import SessionId, TaskId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now
from qwen_research.domain.errors import InvalidTransitionError


class TaskStatus(StrEnum):
    """Lifecycle of a research task.

    The active progression mirrors the canonical deep workflow; ``PAUSED``,
    ``WAITING``, ``FAILED``, ``CANCELLED``, and ``NEEDS_INPUT`` are orthogonal
    control states.
    """

    CREATED = "created"
    CLASSIFIED = "classified"
    PLANNED = "planned"
    RETRIEVING = "retrieving"
    REASONING = "reasoning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    PAUSED = "paused"
    WAITING = "waiting"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_INPUT = "needs_input"


#: Ordered active progression (excludes control/terminal states).
ACTIVE_PROGRESSION: tuple[TaskStatus, ...] = (
    TaskStatus.CREATED,
    TaskStatus.CLASSIFIED,
    TaskStatus.PLANNED,
    TaskStatus.RETRIEVING,
    TaskStatus.REASONING,
    TaskStatus.EXECUTING,
    TaskStatus.VERIFYING,
    TaskStatus.SYNTHESIZING,
    TaskStatus.COMPLETED,
)

TERMINAL_STATES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)

#: States that participate in execution (including terminal outcomes).
EXECUTION_STATES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.CREATED,
        TaskStatus.CLASSIFIED,
        TaskStatus.PLANNED,
        TaskStatus.RETRIEVING,
        TaskStatus.REASONING,
        TaskStatus.EXECUTING,
        TaskStatus.VERIFYING,
        TaskStatus.SYNTHESIZING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
)

#: Control/suspension states. Supported as *domain* states, but not yet fully
#: operated by the runtime (pause/resume is a reserved future capability).
CONTROL_STATES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.PAUSED, TaskStatus.WAITING, TaskStatus.NEEDS_INPUT}
)


def is_terminal_state(status: TaskStatus) -> bool:
    """Return ``True`` for terminal states (no outgoing transitions)."""
    return status in TERMINAL_STATES


def is_control_state(status: TaskStatus) -> bool:
    """Return ``True`` for control/suspension states (PAUSED/WAITING/NEEDS_INPUT)."""
    return status in CONTROL_STATES


def is_execution_state(status: TaskStatus) -> bool:
    """Return ``True`` for execution states (including terminal outcomes)."""
    return status in EXECUTION_STATES


_ALLOWED: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset({TaskStatus.CLASSIFIED, TaskStatus.CANCELLED}),
    TaskStatus.CLASSIFIED: frozenset({TaskStatus.PLANNED, TaskStatus.CANCELLED}),
    TaskStatus.PLANNED: frozenset({TaskStatus.RETRIEVING, TaskStatus.CANCELLED}),
    TaskStatus.RETRIEVING: frozenset(
        {TaskStatus.REASONING, TaskStatus.NEEDS_INPUT, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.REASONING: frozenset(
        {
            TaskStatus.EXECUTING,
            TaskStatus.NEEDS_INPUT,
            TaskStatus.PAUSED,
            TaskStatus.WAITING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.EXECUTING: frozenset(
        {
            TaskStatus.VERIFYING,
            TaskStatus.REASONING,  # retry
            TaskStatus.PAUSED,
            TaskStatus.WAITING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.VERIFYING: frozenset(
        {
            TaskStatus.SYNTHESIZING,
            TaskStatus.RETRIEVING,  # evidence gap → gather more
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.SYNTHESIZING: frozenset({TaskStatus.COMPLETED, TaskStatus.CANCELLED}),
    TaskStatus.NEEDS_INPUT: frozenset(
        {TaskStatus.RETRIEVING, TaskStatus.REASONING, TaskStatus.CANCELLED}
    ),
    TaskStatus.PAUSED: frozenset(
        {TaskStatus.REASONING, TaskStatus.EXECUTING, TaskStatus.CANCELLED}
    ),
    TaskStatus.WAITING: frozenset(
        {TaskStatus.REASONING, TaskStatus.EXECUTING, TaskStatus.CANCELLED}
    ),
    # Terminal states admit no outgoing transitions.
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def validate_transition(current: TaskStatus, new: TaskStatus) -> None:
    """Raise :class:`InvalidTransitionError` if *current* → *new* is illegal."""
    if is_terminal_state(current):
        raise InvalidTransitionError(f"cannot leave terminal state {current.value!r}")
    if new not in _ALLOWED[current]:
        raise InvalidTransitionError(
            f"invalid transition {current.value!r} → {new.value!r}"
        )


def next_active_status(status: TaskStatus) -> TaskStatus | None:
    """Return the next state in the active progression, or ``None``.

    Returns ``None`` at terminal states and for control states (``PAUSED``,
    ``WAITING``, ``FAILED``, ``CANCELLED``, ``NEEDS_INPUT``).
    """
    try:
        index = ACTIVE_PROGRESSION.index(status)
    except ValueError:
        return None
    if index + 1 < len(ACTIVE_PROGRESSION):
        return ACTIVE_PROGRESSION[index + 1]
    return None


@serializable
@dataclasses.dataclass(frozen=True)
class Task:
    """A research request under execution.

    Frozen and value-like: transitions return a new instance rather than
    mutating in place.
    """

    task_id: TaskId
    description: str
    session_id: SessionId
    status: TaskStatus
    reasoning_profile: str
    created_at: datetime
    updated_at: datetime
    parent_task_id: TaskId | None = None
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)

    @classmethod
    def create(
        cls,
        description: str,
        session_id: SessionId,
        reasoning_profile: str,
        *,
        parent_task_id: TaskId | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Task:
        """Create a new task in the ``CREATED`` state."""
        now = utc_now()
        return cls(
            task_id=TaskId(new_id("task")),
            description=description,
            session_id=session_id,
            status=TaskStatus.CREATED,
            reasoning_profile=reasoning_profile,
            created_at=now,
            updated_at=now,
            parent_task_id=parent_task_id,
            metadata=dict(metadata or {}),
        )

    def transition(self, new_status: TaskStatus) -> Task:
        """Return a new ``Task`` in *new_status*, validating the transition."""
        validate_transition(self.status, new_status)
        return dataclasses.replace(self, status=new_status, updated_at=utc_now())

    @property
    def is_terminal(self) -> bool:
        return is_terminal_state(self.status)

    @property
    def is_control_state(self) -> bool:
        return is_control_state(self.status)
