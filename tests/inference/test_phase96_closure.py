"""Phase 9.6 final closure tests: ownership transfer + terminal immutability."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from qwen_research.research.tool_execution import (
    ClaimOutcome,
    LeaseOwnershipError,
    SqliteToolExecutionStore,
    TerminalStateError,
    ToolExecutionIdentity,
    ToolExecutionSemantics,
    ToolExecutionState,
    canonical_arguments_hash,
)
from qwen_research.research.tool_loop import (
    ToolExecutionResult,
    ToolExecutionStatus,
)


def _identity(session: str = "session-1", call: str = "call_1") -> ToolExecutionIdentity:
    return ToolExecutionIdentity(inference_session_id=session, call_id=call)


def _result(
    call_id: str, status: ToolExecutionStatus = ToolExecutionStatus.SUCCEEDED
) -> ToolExecutionResult:
    return ToolExecutionResult(call_id=call_id, tool_name="search_corpus", status=status)


def _fields(**overrides: Any) -> dict[str, Any]:
    f: dict[str, Any] = {
        "tool_name": "search_corpus",
        "arguments_hash": canonical_arguments_hash({"query": "q"}),
        "project_id": "default",
        "session_id": "",
        "task_id": None,
        "run_id": None,
        "execution_semantics": ToolExecutionSemantics.READ_ONLY,
        "permission": "read",
        "lease_id": "lease-a",
        "lease_owner": "A",
        "lease_duration_seconds": 120.0,
    }
    f.update(overrides)
    return f


def test_critical_old_owner_cannot_mutate_after_reclaim(tmp_path: Path) -> None:
    """The exact Phase 9.6 bug: A loses lease, B reclaims+succeeds, A finishes
    and attempts mark_unknown — must be rejected, B's SUCCESS preserved."""
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()

    # A claims (short lease so it can go stale) and starts running.
    store.claim(
        identity, **_fields(lease_id="lease-a", lease_owner="A", lease_duration_seconds=0.01)
    )
    store.mark_running(identity, "lease-a")

    # A's heartbeat stops (simulate). Lease expires → B reclaims.
    import time
    time.sleep(0.05)
    assert store.is_stale(identity) is True
    reclaim = store.reclaim(
        identity, lease_id="lease-b", lease_owner="B", lease_duration_seconds=120.0
    )
    assert reclaim.outcome is ClaimOutcome.CLAIMED
    store.mark_running(identity, "lease-b")
    store.complete(identity, "lease-b", _result("call_1"))

    # A finishes and attempts mark_unknown → rejected.
    with pytest.raises(LeaseOwnershipError):
        store.mark_unknown(identity, "lease-a", "A finished late")
    # A also cannot complete with the old lease.
    with pytest.raises(LeaseOwnershipError):
        store.complete(
            identity, "lease-a", _result("call_1", ToolExecutionStatus.FAILED)
        )

    record = store.inspect(identity)
    assert record is not None
    assert record.state is ToolExecutionState.SUCCEEDED
    assert record.result is not None
    assert record.result.status is ToolExecutionStatus.SUCCEEDED


def test_old_owner_complete_after_reclaim_rejected(tmp_path: Path) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(
        identity, **_fields(lease_id="lease-a", lease_owner="A", lease_duration_seconds=-1.0)
    )
    store.reclaim(
        identity, lease_id="lease-b", lease_owner="B", lease_duration_seconds=120.0
    )
    with pytest.raises(LeaseOwnershipError):
        store.complete(identity, "lease-a", _result("call_1"))


def test_old_owner_heartbeat_after_reclaim_rejected(tmp_path: Path) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(
        identity, **_fields(lease_id="lease-a", lease_owner="A", lease_duration_seconds=-1.0)
    )
    store.reclaim(
        identity, lease_id="lease-b", lease_owner="B", lease_duration_seconds=120.0
    )
    with pytest.raises(LeaseOwnershipError):
        store.heartbeat(identity, "lease-a", 120.0)


def test_old_owner_release_after_reclaim_rejected(tmp_path: Path) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(
        identity, **_fields(lease_id="lease-a", lease_owner="A", lease_duration_seconds=-1.0)
    )
    store.reclaim(
        identity, lease_id="lease-b", lease_owner="B", lease_duration_seconds=120.0
    )
    with pytest.raises(LeaseOwnershipError):
        store.release(identity, "lease-a")


def test_terminal_states_immutable_to_owner_operations(tmp_path: Path) -> None:
    """Every terminal state resists heartbeat/complete/mark_unknown/release."""
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()

    for status, expected_state in [
        (ToolExecutionStatus.SUCCEEDED, ToolExecutionState.SUCCEEDED),
        (ToolExecutionStatus.FAILED, ToolExecutionState.FAILED),
        (ToolExecutionStatus.DENIED, ToolExecutionState.DENIED),
        (ToolExecutionStatus.INVALID_ARGUMENTS, ToolExecutionState.INVALID_ARGUMENTS),
        (ToolExecutionStatus.TIMEOUT, ToolExecutionState.TIMEOUT),
        (ToolExecutionStatus.RESOURCE_LIMIT, ToolExecutionState.RESOURCE_LIMIT),
        (ToolExecutionStatus.CANCELLED, ToolExecutionState.CANCELLED),
    ]:
        identity = ToolExecutionIdentity(inference_session_id="s", call_id=f"c_{status.value}")
        store.claim(identity, **_fields())
        store.mark_running(identity, "lease-a")
        store.complete(identity, "lease-a", _result(identity.call_id, status))
        record = store.inspect(identity)
        assert record is not None and record.state is expected_state, status

        # A still-valid lease cannot mutate a terminal record.
        with pytest.raises(LeaseOwnershipError):
            store.complete(identity, "lease-a", _result(identity.call_id))
        with pytest.raises(LeaseOwnershipError):
            store.heartbeat(identity, "lease-a", 120.0)
        with pytest.raises(LeaseOwnershipError):
            store.mark_unknown(identity, "lease-a", "late")
        with pytest.raises(LeaseOwnershipError):
            store.release(identity, "lease-a")
        # State is unchanged.
        record = store.inspect(identity)
        assert record is not None and record.state is expected_state, status


def test_unknown_is_not_auto_replayed_as_success(tmp_path: Path) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(identity, **_fields())
    store.mark_unknown(identity, "lease-a", "ambiguous")
    replay = store.claim(identity, **_fields(lease_id="lease-b", lease_owner="B"))
    assert replay.outcome is ClaimOutcome.ALREADY_COMPLETED
    # UNKNOWN is never replayed as SUCCESS.
    assert replay.result is None or replay.result.status is not ToolExecutionStatus.SUCCEEDED


def test_current_owner_can_still_mutate(tmp_path: Path) -> None:
    """Phase 9.6 must not make all mutations impossible."""
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(identity, **_fields())
    store.mark_running(identity, "lease-a")
    store.heartbeat(identity, "lease-a", 120.0)
    store.complete(identity, "lease-a", _result("call_1"))
    rec = store.inspect(identity)
    assert rec is not None and rec.state is ToolExecutionState.SUCCEEDED

    # A fresh call: owner can mark_unknown and release.
    identity2 = ToolExecutionIdentity("session-1", "call_2")
    store.claim(identity2, **_fields(lease_id="lease-a"))
    store.mark_unknown(identity2, "lease-a", "owner marks own ambiguous")
    rec2 = store.inspect(identity2)
    assert rec2 is not None and rec2.state is ToolExecutionState.UNKNOWN


def test_recover_unknown_only_on_stale(tmp_path: Path) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(identity, **_fields())  # active lease
    # Not stale → recovery authority may not mark UNKNOWN.
    with pytest.raises(TerminalStateError):
        store.recover_unknown(identity, "premature")
    # A terminal record also cannot be recovered as UNKNOWN.
    store.mark_running(identity, "lease-a")
    store.complete(identity, "lease-a", _result("call_1"))
    with pytest.raises(TerminalStateError):
        store.recover_unknown(identity, "terminal")


def test_scope_conflict_project_mismatch_rejected(tmp_path: Path) -> None:
    store = SqliteToolExecutionStore(tmp_path / "tool.db")
    store.initialize()
    identity = _identity()
    store.claim(identity, **_fields(project_id="proj-a"))
    store.complete(identity, "lease-a", _result("call_1"))
    conflict = store.claim(identity, **_fields(project_id="proj-b"))
    assert conflict.outcome is ClaimOutcome.CONFLICT
