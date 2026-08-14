"""Task lifecycle state categories and reserved control states."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import SessionId
from qwen_research.domain.errors import InvalidTransitionError
from qwen_research.domain.task import (
    CONTROL_STATES,
    EXECUTION_STATES,
    TERMINAL_STATES,
    Task,
    TaskStatus,
    is_control_state,
    is_execution_state,
    is_terminal_state,
)


def test_categories_partition_all_states() -> None:
    all_states = set(TaskStatus)
    assert all_states == EXECUTION_STATES | CONTROL_STATES
    assert EXECUTION_STATES.isdisjoint(CONTROL_STATES)


def test_terminal_states_are_subset_of_execution() -> None:
    assert TERMINAL_STATES <= EXECUTION_STATES


def test_needs_input_is_non_terminal() -> None:
    assert not is_terminal_state(TaskStatus.NEEDS_INPUT)
    assert is_control_state(TaskStatus.NEEDS_INPUT)


def test_control_state_helpers() -> None:
    assert is_control_state(TaskStatus.PAUSED)
    assert is_control_state(TaskStatus.WAITING)
    assert not is_control_state(TaskStatus.COMPLETED)
    assert is_execution_state(TaskStatus.REASONING)
    assert is_execution_state(TaskStatus.COMPLETED)


def test_task_properties() -> None:
    task = Task.create("t", SessionId("s"), "DEEP")
    assert not task.is_terminal
    assert not task.is_control_state


def _walk_to(status: TaskStatus) -> Task:
    from qwen_research.domain.task import ACTIVE_PROGRESSION

    task = Task.create("t", SessionId("s"), "DEEP")
    for state in ACTIVE_PROGRESSION:
        if state is TaskStatus.CREATED:
            continue
        task = task.transition(state)
        if state is status:
            return task
    raise AssertionError(f"could not walk to {status}")


def test_control_state_transitions_are_valid_domain_transitions() -> None:
    # Entering and leaving control states is valid at the domain level, even
    # though the runtime does not yet operate pause/resume (reserved).
    reasoning = _walk_to(TaskStatus.REASONING)
    paused = reasoning.transition(TaskStatus.PAUSED)
    assert paused.status is TaskStatus.PAUSED
    resumed = paused.transition(TaskStatus.REASONING)
    assert resumed.status is TaskStatus.REASONING

    waiting = reasoning.transition(TaskStatus.WAITING)
    assert waiting.status is TaskStatus.WAITING
    assert waiting.transition(TaskStatus.EXECUTING).status is TaskStatus.EXECUTING


def test_invalid_examples_remain_invalid() -> None:
    completed = _walk_to(TaskStatus.COMPLETED)
    for target in (TaskStatus.EXECUTING, TaskStatus.REASONING, TaskStatus.PLANNED):
        with pytest.raises(InvalidTransitionError):
            completed.transition(target)

    task = Task.create("t", SessionId("s"), "DEEP")
    with pytest.raises(InvalidTransitionError):
        task.transition(TaskStatus.COMPLETED)  # CREATED → COMPLETED invalid


def test_terminal_states_admit_no_outgoing_to_control() -> None:
    completed = _walk_to(TaskStatus.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        completed.transition(TaskStatus.PAUSED)
