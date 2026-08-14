"""MCP error normalization."""

from __future__ import annotations

from qwen_research.domain.errors import (
    InferenceError,
    InvalidTransitionError,
    PermissionError,
    PersistenceError,
    UnsupportedOperationError,
    ValidationError,
)
from qwen_research.mcp.errors import INTERNAL_ERROR, INVALID_PARAMS, map_error


def test_validation_error_maps_to_invalid_params() -> None:
    info = map_error(ValidationError("bad"))
    assert info.code == INVALID_PARAMS
    assert "invalid arguments" in info.message
    assert info.category == "validation"


def test_invalid_transition_maps_to_invalid_params() -> None:
    info = map_error(InvalidTransitionError("nope"))
    assert info.code == INVALID_PARAMS
    assert info.category == "state"


def test_permission_error_maps_to_denied() -> None:
    info = map_error(PermissionError("no"))
    assert info.code == INVALID_PARAMS
    assert "permission denied" in info.message
    assert info.category == "permission"


def test_unsupported_operation_maps_to_unavailable() -> None:
    info = map_error(UnsupportedOperationError("not yet"))
    assert info.code == INTERNAL_ERROR
    assert "capability unavailable" in info.message
    assert info.category == "unsupported"


def test_persistence_error_maps_to_internal() -> None:
    info = map_error(PersistenceError("missing"))
    assert info.code == INTERNAL_ERROR
    assert info.category == "persistence"


def test_inference_error_maps_to_internal() -> None:
    info = map_error(InferenceError("cannot"))
    assert info.code == INTERNAL_ERROR
    assert info.category == "inference"


def test_unknown_error_maps_to_generic_internal() -> None:
    info = map_error(RuntimeError("unexpected"))
    assert info.code == INTERNAL_ERROR
    assert info.message == "internal error"
    assert info.category == "domain"
