"""Qwen endpoint profiles, availability resolution, and model diagnostics.

Separates *which model exists* (the catalog in :mod:`qwen_models`) from *where
and under what conditions it is reachable* (endpoint + region + plan). A model
that exists in the catalog is **not** assumed to be available on every
DashScope endpoint: availability is resolved contextually.

    model_id + endpoint_profile + plan + region
        → AvailabilityResult
        → effective capabilities

No credentials and no hidden chain-of-thought live here.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum

from qwen_research.common.serialization import serializable
from qwen_research.domain.inference import (
    AvailabilityPlan,
    ModelAvailability,
    ModelLifecycle,
    ThinkingMode,
)
from qwen_research.inference.providers.qwen_models import (
    QWEN_MODEL_TABLE,
    QWEN_MODELS,
    QwenApiSurface,
    QwenModelSpec,
)


class AvailabilityStatus(StrEnum):
    """Outcome of resolving a model against an endpoint/plan/region."""

    AVAILABLE = "available"
    PLAN_UNAVAILABLE = "plan_unavailable"
    REGION_UNAVAILABLE = "region_unavailable"
    ENDPOINT_UNAVAILABLE = "endpoint_unavailable"
    MODEL_UNKNOWN = "model_unknown"
    DEPRECATED = "deprecated"


@serializable
@dataclasses.dataclass(frozen=True)
class AvailabilityResult:
    """The resolved availability of a model in a specific context."""

    status: AvailabilityStatus
    model: str
    lifecycle: ModelLifecycle = ModelLifecycle.UNKNOWN
    availability: ModelAvailability = ModelAvailability.UNKNOWN
    plan: AvailabilityPlan | None = None
    region: str = ""
    endpoint_id: str = ""
    reason: str = ""

    @property
    def is_available(self) -> bool:
        return self.status is AvailabilityStatus.AVAILABLE

    def raise_if_unavailable(self, *, unknown_ok: bool = True) -> None:
        """Raise a typed error unless available (or unknown, when permitted).

        ``unknown_ok=True`` treats a catalog miss as non-fatal: unknown models
        may still be usable with conservative capabilities. The endpoint/plan/
        region/deprecated cases always raise their distinct error type.
        """
        from qwen_research.domain.errors import (
            ModelEndpointUnavailableError,
            ModelPlanUnavailableError,
            ModelRegionUnavailableError,
            ModelUnavailableError,
            UnknownModelError,
        )

        if self.status is AvailabilityStatus.MODEL_UNKNOWN:
            if not unknown_ok:
                raise UnknownModelError(f"unknown model {self.model!r}")
            return
        if self.status is AvailabilityStatus.PLAN_UNAVAILABLE:
            raise ModelPlanUnavailableError(self.reason)
        if self.status is AvailabilityStatus.REGION_UNAVAILABLE:
            raise ModelRegionUnavailableError(self.reason)
        if self.status is AvailabilityStatus.ENDPOINT_UNAVAILABLE:
            raise ModelEndpointUnavailableError(self.reason)
        if self.status is AvailabilityStatus.DEPRECATED:
            raise ModelUnavailableError(self.reason)


@serializable
@dataclasses.dataclass(frozen=True)
class QwenEndpointProfile:
    """A named Qwen endpoint/surface with its plan and model restrictions.

    ``model_allowlist`` empty means "all catalog models"; non-empty restricts
    the endpoint to the listed model ids. ``plans`` lists the plans this
    endpoint serves.
    """

    endpoint_id: str
    base_url: str
    region: str = "global"
    api_surface: QwenApiSurface = QwenApiSurface.OPENAI_COMPATIBLE_CHAT
    plans: tuple[AvailabilityPlan, ...] = (AvailabilityPlan.STANDARD,)
    model_allowlist: tuple[str, ...] = ()
    notes: str = ""


#: Models the standard DashScope endpoint serves: the PUBLIC (GA) line-up only.
#: Preview / plan-restricted models (e.g. ``qwen3.8-max-preview``) are excluded.
_STANDARD_ALLOWLIST = tuple(
    s.model for s in QWEN_MODELS if s.availability is ModelAvailability.PUBLIC
)

#: Standard DashScope OpenAI-compatible endpoint (international).
STANDARD_DASHSCOPE = QwenEndpointProfile(
    endpoint_id="dashscope-intl",
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    region="global",
    api_surface=QwenApiSurface.OPENAI_COMPATIBLE_CHAT,
    plans=(AvailabilityPlan.STANDARD,),
    model_allowlist=_STANDARD_ALLOWLIST,
)

#: QwenCloud Token Plan endpoint (Chat Completions surface). Verified to serve
#: the ``qwen3.8-max-preview`` model.
TOKEN_PLAN = QwenEndpointProfile(
    endpoint_id="token-plan",
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    region="global",
    api_surface=QwenApiSurface.TOKEN_PLAN,
    plans=(AvailabilityPlan.TOKEN_PLAN,),
    model_allowlist=("qwen3.8-max-preview",),
    notes="Token Plan; exposes preview models such as qwen3.8-max-preview.",
)

#: Default endpoint profiles by id (operators may override / add their own).
ENDPOINT_PROFILES: dict[str, QwenEndpointProfile] = {
    STANDARD_DASHSCOPE.endpoint_id: STANDARD_DASHSCOPE,
    TOKEN_PLAN.endpoint_id: TOKEN_PLAN,
}


class QwenModelAvailabilityResolver:
    """Resolve a model id to an availability outcome for a context.

    ``catalog`` and ``endpoint_profiles`` are injectable for tests/operators.
    """

    def __init__(
        self,
        catalog: dict[str, QwenModelSpec] | None = None,
        endpoint_profiles: dict[str, QwenEndpointProfile] | None = None,
    ) -> None:
        self._catalog = catalog if catalog is not None else QWEN_MODEL_TABLE
        self._endpoint_profiles = (
            endpoint_profiles if endpoint_profiles is not None else ENDPOINT_PROFILES
        )

    def resolve(
        self,
        model_id: str,
        *,
        endpoint_profile: QwenEndpointProfile | None = None,
        plan: AvailabilityPlan | None = None,
        region: str | None = None,
    ) -> AvailabilityResult:
        spec = self._catalog.get(model_id)
        if spec is None:
            return AvailabilityResult(
                status=AvailabilityStatus.MODEL_UNKNOWN,
                model=model_id,
                endpoint_id=endpoint_profile.endpoint_id if endpoint_profile else "",
                reason="model id is not in the catalog",
            )

        if spec.lifecycle is ModelLifecycle.RETIRED:
            return AvailabilityResult(
                status=AvailabilityStatus.DEPRECATED,
                model=model_id,
                lifecycle=spec.lifecycle,
                availability=spec.availability,
                reason="model is retired",
            )

        endpoint_id = endpoint_profile.endpoint_id if endpoint_profile else ""
        if (
            endpoint_profile is not None
            and endpoint_profile.model_allowlist
            and model_id not in endpoint_profile.model_allowlist
        ):
            return AvailabilityResult(
                status=AvailabilityStatus.ENDPOINT_UNAVAILABLE,
                model=model_id,
                lifecycle=spec.lifecycle,
                availability=spec.availability,
                endpoint_id=endpoint_id,
                reason=f"model not exposed by endpoint {endpoint_id!r}",
            )

        # Derive the effective plan from the endpoint when not given explicitly.
        effective_plan = plan
        if (
            effective_plan is None
            and endpoint_profile is not None
            and len(endpoint_profile.plans) == 1
        ):
            effective_plan = endpoint_profile.plans[0]

        if effective_plan is not None and spec.plans and effective_plan not in spec.plans:
            return AvailabilityResult(
                status=AvailabilityStatus.PLAN_UNAVAILABLE,
                model=model_id,
                lifecycle=spec.lifecycle,
                availability=spec.availability,
                plan=effective_plan,
                endpoint_id=endpoint_id,
                reason=f"model not available under plan {effective_plan.value!r}",
            )

        if region is not None and spec.regions and region not in spec.regions:
            return AvailabilityResult(
                status=AvailabilityStatus.REGION_UNAVAILABLE,
                model=model_id,
                lifecycle=spec.lifecycle,
                availability=spec.availability,
                region=region or "",
                endpoint_id=endpoint_id,
                reason=f"model not available in region {region!r}",
            )

        return AvailabilityResult(
            status=AvailabilityStatus.AVAILABLE,
            model=model_id,
            lifecycle=spec.lifecycle,
            availability=spec.availability,
            plan=effective_plan,
            region=region or "",
            endpoint_id=endpoint_id,
        )

    def require_available(
        self,
        model_id: str,
        *,
        endpoint_profile: QwenEndpointProfile | None = None,
        plan: AvailabilityPlan | None = None,
        region: str | None = None,
    ) -> AvailabilityResult:
        """Resolve and raise a typed error unless the model is available.

        Unlike the provider's permissive dispatch path, this treats an unknown
        model as fatal (``UnknownModelError``).
        """
        result = self.resolve(
            model_id,
            endpoint_profile=endpoint_profile,
            plan=plan,
            region=region,
        )
        result.raise_if_unavailable(unknown_ok=False)
        return result


def resolve_endpoint_profile(
    endpoint_id: str,
    profiles: dict[str, QwenEndpointProfile] | None = None,
) -> QwenEndpointProfile | None:
    """Look up an endpoint profile by id (``None`` for unknown id)."""
    table = profiles if profiles is not None else ENDPOINT_PROFILES
    return table.get(endpoint_id)


def resolve_plan(name: str | None) -> AvailabilityPlan | None:
    """Map a plan name to :class:`AvailabilityPlan` (``None`` when unset/unknown)."""
    if not name:
        return None
    for plan in AvailabilityPlan:
        if plan.value == name:
            return plan
    return None


@dataclasses.dataclass(frozen=True)
class ModelDiagnostic:
    """A provider diagnostic describing a model and its effective capabilities."""

    model: str
    lifecycle: ModelLifecycle
    availability: ModelAvailability
    endpoint_id: str
    region: str
    plan: AvailabilityPlan | None
    thinking_mode: ThinkingMode
    capability_source: str
    effective_capabilities: dict[str, bool]
    notes: str = ""

    def render(self) -> str:
        lines = [
            f"Model: {self.model}",
            f"Lifecycle: {self.lifecycle.value.upper()}",
            f"Availability: {self.availability.value.upper()}",
            f"Endpoint: {self.endpoint_id or '(default)'}",
            f"Region: {self.region or '(default)'}",
            f"Plan: {self.plan.value.upper() if self.plan else '(none)'}",
            f"Thinking: {self.thinking_mode.value.upper()}",
            f"Capability source: {self.capability_source}",
            "Capabilities:",
        ]
        for name in sorted(self.effective_capabilities):
            value = self.effective_capabilities[name]
            lines.append(f"  {name} = {'APPLY' if value else 'unsupported'}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        return "\n".join(lines)
