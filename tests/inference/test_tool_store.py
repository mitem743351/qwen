"""Tool-execution store tests (Phase 9.4 claim/lease protocol)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from qwen_research.research.tool_execution import (
    CallIdConflictError,
    ClaimOutcome,
    InMemoryToolExecutionStore,
    LeaseOwnershipError,
    SqliteToolExecutionStore,
    ToolExecutionIdentity,
    ToolExecutionSemantics,
    ToolExecutionState,
    ToolExecutionStore,
    canonical_arguments_hash,
)
from qwen_research.research.tool_loop import (
    ToolExecutionResult,
    ToolExecutionStatus,
)


def _result(
    call_id: str, *, status: ToolExecutionStatus = ToolExecutionStatus.SUCCEEDED
) -> ToolExecutionResult:
    return ToolExecutionResult(
        call_id=call_id,
        tool_name="search_corpus",
        status=status,
        content="bounded result",
        structured_data={"rows": 3},
        provenance={"tool": "search_corpus"},
    )


def _identity(session: str = "session-1", call: str = "call_1") -> ToolExecutionIdentity:
    return ToolExecutionIdentity(inference_session_id=session, call_id=call)


def _claim_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "tool_name": "search_corpus",
        "arguments_hash": canonical_arguments_hash({"query": "q"}),
        "project_id": "default",
        "session_id": "",
        "task_id": None,
        "run_id": None,
        "execution_semantics": ToolExecutionSemantics.READ_ONLY,
        "permission": "read",
        "lease_id": "lease-1",
        "lease_owner": "executor-1",
        "lease_duration_seconds": 120.0,
    }
    fields.update(overrides)
    return fields


@pytest.fixture(params=["in_memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ToolExecutionStore:
    if request.param == "in_memory":
        return InMemoryToolExecutionStore()
    s = SqliteToolExecutionStore(tmp_path / "tool_exec.db")
    s.initialize()
    return s


def test_first_claim_then_complete_then_replay(store: ToolExecutionStore) -> None:
    identity = _identity()
    claim = store.claim(identity, **_claim_fields())
    assert claim.outcome is ClaimOutcome.CLAIMED

    store.mark_running(identity, "lease-1")
    store.complete(identity, "lease-1", _result("call_1"))

    # Re-claim the completed identity → replayed result, no re-execution.
    replay = store.claim(identity, **_claim_fields(lease_id="lease-2", lease_owner="executor-2"))
    assert replay.outcome is ClaimOutcome.ALREADY_COMPLETED
    assert replay.result is not None
    assert replay.result.status is ToolExecutionStatus.SUCCEEDED


def test_concurrent_claim_only_one_owner(store: ToolExecutionStore) -> None:
    identity = _identity()
    first = store.claim(identity, **_claim_fields(lease_id="lease-a", lease_owner="A"))
    second = store.claim(identity, **_claim_fields(lease_id="lease-b", lease_owner="B"))
    assert first.outcome is ClaimOutcome.CLAIMED
    assert second.outcome is ClaimOutcome.ALREADY_CLAIMED


def test_call_id_conflict_different_arguments(store: ToolExecutionStore) -> None:
    identity = _identity()
    store.claim(identity, **_claim_fields())
    store.complete(identity, "lease-1", _result("call_1"))
    conflict = store.claim(
        identity, **_claim_fields(arguments_hash=canonical_arguments_hash({"query": "OTHER"}))
    )
    assert conflict.outcome is ClaimOutcome.CONFLICT


def test_call_id_conflict_different_tool(store: ToolExecutionStore) -> None:
    identity = _identity()
    store.claim(identity, **_claim_fields())
    store.complete(identity, "lease-1", _result("call_1"))
    conflict = store.claim(identity, **_claim_fields(tool_name="run_analysis"))
    assert conflict.outcome is ClaimOutcome.CONFLICT


def test_call_id_conflict_different_project(store: ToolExecutionStore) -> None:
    identity = _identity()
    store.claim(identity, **_claim_fields())
    store.complete(identity, "lease-1", _result("call_1"))
    conflict = store.claim(identity, **_claim_fields(project_id="other-project"))
    assert conflict.outcome is ClaimOutcome.CONFLICT


def test_wrong_lease_owner_rejected(store: ToolExecutionStore) -> None:
    identity = _identity()
    store.claim(identity, **_claim_fields(lease_id="lease-a", lease_owner="A"))
    with pytest.raises(LeaseOwnershipError):
        store.complete(identity, "lease-wrong", _result("call_1"))


def test_expired_lease_cannot_complete(store: ToolExecutionStore) -> None:
    identity = _identity()
    store.claim(identity, **_claim_fields(lease_id="lease-1", lease_duration_seconds=-1.0))
    with pytest.raises(LeaseOwnershipError):
        store.complete(identity, "lease-1", _result("call_1"))


def test_stale_claim_detected_and_reclaimed(store: ToolExecutionStore) -> None:
    identity = _identity()
    store.claim(identity, **_claim_fields(lease_id="lease-1", lease_duration_seconds=-1.0))
    assert store.is_stale(identity) is True
    reclaim = store.reclaim(
        identity, lease_id="lease-2", lease_owner="B", lease_duration_seconds=120.0
    )
    assert reclaim.outcome is ClaimOutcome.CLAIMED
    store.complete(identity, "lease-2", _result("call_1"))


def test_mark_unknown_records_ambiguous_outcome(store: ToolExecutionStore) -> None:
    identity = _identity()
    store.claim(identity, **_claim_fields())
    store.mark_unknown(identity, "crash before completion")
    record = store.inspect(identity)
    assert record is not None
    assert record.state is ToolExecutionState.UNKNOWN
    # A subsequent claim must NOT replay UNKNOWN as success.
    replay = store.claim(identity, **_claim_fields())
    assert replay.outcome is ClaimOutcome.ALREADY_COMPLETED
    assert replay.result is None or replay.result.status is not ToolExecutionStatus.SUCCEEDED


def test_sqlite_restart_replay(tmp_path: Path) -> None:
    path = tmp_path / "tool_exec.db"
    identity = _identity()
    with SqliteToolExecutionStore(path) as store_a:
        store_a.claim(identity, **_claim_fields())
        store_a.complete(identity, "lease-1", _result("call_1"))

    with SqliteToolExecutionStore(path) as store_b:
        replay = store_b.claim(identity, **_claim_fields(lease_id="lease-2", lease_owner="B"))
        assert replay.outcome is ClaimOutcome.ALREADY_COMPLETED
        assert replay.result is not None
        assert replay.result.status is ToolExecutionStatus.SUCCEEDED


def test_sqlite_migration_preserves_legacy_results(tmp_path: Path) -> None:
    """A Phase 9.3 ``tool_executions`` cache is migrated without data loss."""
    import sqlite3

    from qwen_research.common.serialization import dumps

    path = tmp_path / "tool_exec.db"
    legacy = sqlite3.connect(str(path))
    legacy.execute(
        "CREATE TABLE tool_executions (inference_session_id TEXT NOT NULL, "
        "call_id TEXT NOT NULL, data TEXT NOT NULL, "
        "PRIMARY KEY (inference_session_id, call_id))"
    )
    legacy.execute(
        "INSERT INTO tool_executions VALUES (?, ?, ?)",
        ("session-1", "call_1", dumps(_result("call_1"))),
    )
    legacy.commit()
    legacy.close()

    with SqliteToolExecutionStore(path) as store:
        replay = store.claim(_identity(), **_claim_fields())
        assert replay.outcome is ClaimOutcome.ALREADY_COMPLETED
        assert replay.result is not None
        assert replay.result.status is ToolExecutionStatus.SUCCEEDED


def test_error_classes_are_tool_errors() -> None:
    from qwen_research.domain.errors import ToolError as DomainToolError

    assert issubclass(LeaseOwnershipError, DomainToolError)
    assert issubclass(CallIdConflictError, DomainToolError)
