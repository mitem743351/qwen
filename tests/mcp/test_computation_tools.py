"""MCP computation tool permissions and runtime integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from computation_helpers import build_service, ref
from qwen_research.computation.models import ComputationOperation, DatasetReference
from qwen_research.domain.errors import UnsupportedOperationError
from qwen_research.mcp.permissions import DEFAULT_TOOL_PERMISSIONS, MCPPermission
from qwen_research.research.runtime import InMemoryResearchRuntime


def test_computation_tool_permissions() -> None:
    assert DEFAULT_TOOL_PERMISSIONS["describe_dataset"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["get_computation_result"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["run_query"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["run_analysis"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["run_python"] is MCPPermission.EXECUTE


def test_runtime_computation_roundtrip(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    runtime = InMemoryResearchRuntime(computation=service)

    profile = runtime.describe_dataset(ref(data, "numbers.csv"))
    assert profile.row_count == 5

    result = runtime.run_analysis(
        "p", (ref(data, "numbers.csv"),), ComputationOperation.STATISTICS, {"column": "value"}
    )
    assert result.status.value == "completed"
    loaded = runtime.get_computation_result("p", result.computation_id)
    assert loaded.computation_id == result.computation_id


def test_runtime_computation_unavailable(tmp_path: Path) -> None:
    runtime = InMemoryResearchRuntime()
    with pytest.raises(UnsupportedOperationError):
        runtime.describe_dataset(DatasetReference(root_id="r", relative_path="x.csv"))
    with pytest.raises(UnsupportedOperationError):
        runtime.get_computation_result("p", "computation_1")
