"""Tool-execution store tests (Phase 9.3)."""

from __future__ import annotations

from pathlib import Path

from qwen_research.research.tool_loop import (
    ToolError,
    ToolErrorCode,
    ToolExecutionResult,
    ToolExecutionStatus,
)
from qwen_research.research.tool_store import (
    InMemoryToolExecutionStore,
    SqliteToolExecutionStore,
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


def test_in_memory_store_roundtrip() -> None:
    store = InMemoryToolExecutionStore()
    store.save("session-1", "call_1", _result("call_1"))
    got = store.get("session-1", "call_1")
    assert got is not None
    assert got.call_id == "call_1"
    assert got.status is ToolExecutionStatus.SUCCEEDED
    assert store.get("session-1", "missing") is None
    assert store.get("other-session", "call_1") is None


def test_sqlite_store_roundtrip_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "tool_executions.db"
    with SqliteToolExecutionStore(path) as store:
        store.save("session-1", "call_1", _result("call_1"))
        store.save(
            "session-1",
            "call_2",
            _result("call_2", status=ToolExecutionStatus.DENIED),
        )

    # Reopen on the same path (simulated restart): results survive.
    with SqliteToolExecutionStore(path) as reopened:
        got = reopened.get("session-1", "call_1")
        assert got is not None
        assert got.status is ToolExecutionStatus.SUCCEEDED
        denied = reopened.get("session-1", "call_2")
        assert denied is not None
        assert denied.status is ToolExecutionStatus.DENIED
        assert reopened.get("session-1", "missing") is None


def test_sqlite_store_persists_error_and_provenance(tmp_path: Path) -> None:
    path = tmp_path / "tool_executions.db"
    result = ToolExecutionResult(
        call_id="call_1",
        tool_name="search_corpus",
        status=ToolExecutionStatus.INVALID_ARGUMENTS,
        error=ToolError(ToolErrorCode.INVALID_ARGUMENTS, "malformed"),
        provenance={"tool": "search_corpus", "project_id": "p1"},
    )
    with SqliteToolExecutionStore(path) as store:
        store.save("session-1", "call_1", result)

    with SqliteToolExecutionStore(path) as store:
        got = store.get("session-1", "call_1")
        assert got is not None
        assert got.status is ToolExecutionStatus.INVALID_ARGUMENTS
        assert got.error is not None
        assert got.error.code is ToolErrorCode.INVALID_ARGUMENTS
        assert got.provenance == {"tool": "search_corpus", "project_id": "p1"}
