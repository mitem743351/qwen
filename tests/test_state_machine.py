"""Task state machine: transitions, terminal states, pause/resume."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import SessionId
from qwen_research.domain.errors import InvalidTransitionError
from qwen_research.domain.task import Task, TaskStatus, next_active_status


def _task(status: TaskStatus | None = None) -> Task:
    task = Task.create("t", SessionId("s"), "DEEP")
    if status is not None:
        # Walk to the desired state via valid transitions only.
        for step in next_steps_to(status):
            task = task.transition(step)
    return task


def next_steps_to(target: TaskStatus) -> list[TaskStatus]:
    from qwen_research.domain.task import ACTIVE_PROGRESSION

    steps: list[TaskStatus] = []
    current = TaskStatus.CREATED
    for state in ACTIVE_PROGRESSION:
        if state is current:
            continue
        steps.append(state)
        if state is target:
            break
        current = state
    return steps


def test_forward_progression() -> None:
    task = Task.create("t", SessionId("s"), "DEEP")
    for state in (
        TaskStatus.CLASSIFIED,
        TaskStatus.PLANNED,
        TaskStatus.RETRIEVING,
        TaskStatus.REASONING,
        TaskStatus.EXECUTING,
        TaskStatus.VERIFYING,
        TaskStatus.SYNTHESIZING,
        TaskStatus.COMPLETED,
    ):
        task = task.transition(state)
    assert task.is_terminal


def test_invalid_transition_raises() -> None:
    task = Task.create("t", SessionId("s"), "DEEP")
    with pytest.raises(InvalidTransitionError):
        task.transition(TaskStatus.COMPLETED)  # skips required stages


def test_terminal_states_admit_no_outgoing() -> None:
    completed = _task(TaskStatus.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        completed.transition(TaskStatus.CLASSIFIED)


def test_verification_can_loop_to_retrieving() -> None:
    task = _task(TaskStatus.VERIFYING)
    task = task.transition(TaskStatus.RETRIEVING)  # evidence gap
    assert task.status is TaskStatus.RETRIEVING


def test_cancellation_from_active_state() -> None:
    task = _task(TaskStatus.REASONING)
    task = task.transition(TaskStatus.CANCELLED)
    assert task.is_terminal


def test_needs_input_and_resume() -> None:
    task = _task(TaskStatus.RETRIEVING)
    task = task.transition(TaskStatus.NEEDS_INPUT)
    assert task.status is TaskStatus.NEEDS_INPUT
    task = task.transition(TaskStatus.REASONING)
    assert task.status is TaskStatus.REASONING


def test_next_active_status() -> None:
    assert next_active_status(TaskStatus.PLANNED) is TaskStatus.RETRIEVING
    assert next_active_status(TaskStatus.COMPLETED) is None
    assert next_active_status(TaskStatus.PAUSED) is None
