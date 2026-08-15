"""Qwen endpoint/plan/region availability resolution (Phase 8.3)."""

from __future__ import annotations

import pytest

from qwen_research.domain.errors import (
    ModelEndpointUnavailableError,
    ModelPlanUnavailableError,
    ModelRegionUnavailableError,
    UnknownModelError,
)
from qwen_research.domain.inference import (
    AvailabilityPlan,
    ModelAvailability,
    ModelLifecycle,
)
from qwen_research.inference.providers.qwen_availability import (
    STANDARD_DASHSCOPE,
    TOKEN_PLAN,
    AvailabilityStatus,
    QwenEndpointProfile,
    QwenModelAvailabilityResolver,
)
from qwen_research.inference.providers.qwen_models import QwenModelSpec


def test_qwen_38_preview_available_on_token_plan() -> None:
    resolver = QwenModelAvailabilityResolver()
    result = resolver.resolve("qwen3.8-max-preview", plan=AvailabilityPlan.TOKEN_PLAN)
    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.lifecycle is ModelLifecycle.PREVIEW
    assert result.availability is ModelAvailability.PLAN_RESTRICTED


def test_qwen_38_preview_plan_restricted() -> None:
    resolver = QwenModelAvailabilityResolver()
    result = resolver.resolve("qwen3.8-max-preview", plan=AvailabilityPlan.STANDARD)
    assert result.status is AvailabilityStatus.PLAN_UNAVAILABLE


def test_qwen_38_preview_not_on_standard_endpoint() -> None:
    resolver = QwenModelAvailabilityResolver()
    result = resolver.resolve("qwen3.8-max-preview", endpoint_profile=STANDARD_DASHSCOPE)
    assert result.status is AvailabilityStatus.ENDPOINT_UNAVAILABLE


def test_qwen_38_preview_on_token_plan_endpoint() -> None:
    resolver = QwenModelAvailabilityResolver()
    result = resolver.resolve("qwen3.8-max-preview", endpoint_profile=TOKEN_PLAN)
    assert result.status is AvailabilityStatus.AVAILABLE


def test_qwen_37_max_on_standard_endpoint() -> None:
    resolver = QwenModelAvailabilityResolver()
    result = resolver.resolve("qwen3.7-max", endpoint_profile=STANDARD_DASHSCOPE)
    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.lifecycle is ModelLifecycle.GA


def test_unknown_model_status() -> None:
    resolver = QwenModelAvailabilityResolver()
    result = resolver.resolve("new-qwen-model")
    assert result.status is AvailabilityStatus.MODEL_UNKNOWN


def test_retired_model_is_deprecated() -> None:
    catalog = {
        "qwen-old": QwenModelSpec(model="qwen-old", lifecycle=ModelLifecycle.RETIRED)
    }
    resolver = QwenModelAvailabilityResolver(catalog=catalog)
    result = resolver.resolve("qwen-old")
    assert result.status is AvailabilityStatus.DEPRECATED


def test_region_restriction() -> None:
    catalog = {
        "qwen-regional": QwenModelSpec(model="qwen-regional", regions=("cn",))
    }
    resolver = QwenModelAvailabilityResolver(catalog=catalog)
    assert resolver.resolve("qwen-regional", region="cn").status is AvailabilityStatus.AVAILABLE
    assert (
        resolver.resolve("qwen-regional", region="us").status
        is AvailabilityStatus.REGION_UNAVAILABLE
    )


def test_require_available_raises_distinct_errors() -> None:
    resolver = QwenModelAvailabilityResolver()

    with pytest.raises(ModelPlanUnavailableError):
        resolver.require_available("qwen3.8-max-preview", plan=AvailabilityPlan.STANDARD)

    with pytest.raises(ModelEndpointUnavailableError):
        resolver.require_available("qwen3.8-max-preview", endpoint_profile=STANDARD_DASHSCOPE)

    with pytest.raises(UnknownModelError):
        resolver.require_available("new-qwen-model")


def test_raise_if_unavailable_unknown_ok() -> None:
    resolver = QwenModelAvailabilityResolver()
    result = resolver.resolve("new-qwen-model")
    # Unknown is non-fatal by default (permissive dispatch path).
    result.raise_if_unavailable(unknown_ok=True)

    catalog = {
        "qwen-regional": QwenModelSpec(model="qwen-regional", regions=("cn",))
    }
    regional = QwenModelAvailabilityResolver(catalog=catalog)
    with pytest.raises(ModelRegionUnavailableError):
        regional.resolve("qwen-regional", region="us").raise_if_unavailable()


def test_endpoint_allowlist_is_positive() -> None:
    endpoint = QwenEndpointProfile(
        endpoint_id="custom",
        base_url="https://example.invalid/v1",
        model_allowlist=("qwen3.7-max",),
    )
    resolver = QwenModelAvailabilityResolver()
    assert resolver.resolve("qwen3.7-max", endpoint_profile=endpoint).is_available
    assert (
        resolver.resolve("qwen3.7-plus", endpoint_profile=endpoint).status
        is AvailabilityStatus.ENDPOINT_UNAVAILABLE
    )
