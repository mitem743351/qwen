"""Model-specific capability discovery for the Qwen adapter (Phases 8.1–8.3)."""

from __future__ import annotations

from inference_helpers import completion_response, make_provider
from qwen_research.domain.inference import (
    AvailabilityPlan,
    ModelAvailability,
    ModelInfo,
    ModelLifecycle,
)
from qwen_research.inference.providers.qwen_models import (
    QWEN_MODEL_TABLE,
    QWEN_MODELS,
    QwenModelSpec,
    resolve_spec,
)


def test_catalog_is_model_specific() -> None:
    specs = {s.model: s for s in QWEN_MODELS}
    # Qwen3-era flagships support numeric thinking_budget.
    assert specs["qwen3.7-max"].thinking is True
    assert specs["qwen3.7-max"].thinking_budget is True
    assert specs["qwen3.7-max"].context_window == 1_000_000
    # Qwen2.5-era qwen-max is hybrid thinking but has no numeric budget.
    assert specs["qwen-max"].thinking is True
    assert specs["qwen-max"].thinking_budget is False
    assert specs["qwen-max"].context_window == 32_768


def test_qwen_37_max_documented_capabilities() -> None:
    """qwen3.7-max capabilities match the official 2026 documentation."""
    spec = QWEN_MODEL_TABLE["qwen3.7-max"]
    assert spec.context_window == 1_000_000
    assert spec.max_output_tokens == 65_536
    assert spec.thinking is True
    assert spec.thinking_budget is True
    assert spec.preserve_thinking is True
    assert spec.structured_output is True
    assert spec.tool_calling is True
    assert spec.streaming is True


def test_qwen_38_max_preview_is_listed_as_preview() -> None:
    spec = QWEN_MODEL_TABLE["qwen3.8-max-preview"]
    assert spec.lifecycle is ModelLifecycle.PREVIEW
    assert spec.availability is ModelAvailability.PLAN_RESTRICTED
    assert spec.plans == (AvailabilityPlan.TOKEN_PLAN,)
    assert spec.thinking is True
    assert spec.thinking_always_enabled is True
    assert spec.tool_calling is True
    assert spec.structured_output is False  # always-on thinking → no structured output
    assert spec.context_window == 983_616
    assert spec.max_output_tokens == 131_072
    assert set(spec.reasoning_effort_levels) == {"low", "medium", "xhigh"}
    assert spec.builtin_web_search is True
    assert spec.builtin_code_interpreter is True
    assert spec.builtin_web_scraping is True


def test_qwen_38_max_ga_is_not_listed() -> None:
    # Only the *preview* id is cataloged; the GA id is not asserted.
    assert "qwen3.8-max" not in QWEN_MODEL_TABLE
    assert "qwen3.8-max" not in {s.model for s in QWEN_MODELS}


def test_preserve_thinking_is_model_specific() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    assert provider.capabilities("qwen3.7-max").supports_preserved_thinking is True
    assert provider.capabilities("qwen3.7-plus").supports_preserved_thinking is True
    # Other models (even Qwen3.x) do not support preserve_thinking.
    assert provider.capabilities("qwen3.6-plus").supports_preserved_thinking is False
    assert provider.capabilities("qwen-max").supports_preserved_thinking is False


def test_structured_output_and_tool_calling_are_model_specific() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    # Hybrid chat models support both.
    assert provider.capabilities("qwen3.7-max").supports_structured_output is True
    assert provider.capabilities("qwen3.7-max").supports_tool_calling is True
    # Thinking-only qwq models support neither (no non-thinking mode).
    assert provider.capabilities("qwq-32b").supports_structured_output is False
    assert provider.capabilities("qwq-32b").supports_tool_calling is False


def test_streaming_is_uniformly_supported() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    for model in ("qwen3.7-max", "qwen-max", "qwq-32b"):
        assert provider.capabilities(model).supports_streaming is True


def test_capabilities_depend_on_model() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    # qwen3.7-max → reasoning budget supported.
    thinking_caps = provider.capabilities("qwen3.7-max")
    assert thinking_caps.supports_reasoning is True
    assert thinking_caps.supports_reasoning_budget is True
    # qwen-max → reasoning supported, budget not.
    hybrid_caps = provider.capabilities("qwen-max")
    assert hybrid_caps.supports_reasoning is True
    assert hybrid_caps.supports_reasoning_budget is False
    # Unknown model → conservative (no reasoning assumed).
    unknown_caps = provider.capabilities("qwen-future-unknown")
    assert unknown_caps.supports_reasoning is False
    assert unknown_caps.supports_reasoning_budget is False


def test_model_info_is_model_specific() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    info = provider.model_info("qwen3.7-max")
    assert info.context_window == 1_000_000
    assert info.model == "qwen3.7-max"
    assert info.provider == "qwen"


def test_models_lists_catalog_plus_default() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    models = provider.models()
    ids = {m.model for m in models}
    assert "qwen-max" in ids  # the configured default
    assert "qwen3.7-max" in ids
    assert all(isinstance(m, ModelInfo) for m in models)


def test_resolve_spec_falls_back_conservatively() -> None:
    spec = resolve_spec("qwen-brand-new")
    assert isinstance(spec, QwenModelSpec)
    assert spec.model == "qwen-brand-new"
    assert spec.thinking is False
    assert spec.thinking_budget is False
    assert spec.context_window is None


def test_operator_can_override_catalog() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    custom = {
        "qwen-custom": QwenModelSpec(model="qwen-custom", thinking=True, thinking_budget=True)
    }
    # Rebuild the provider with an explicit catalog override.
    from qwen_research.inference.config import ProviderConfig
    from qwen_research.inference.providers.qwen import QwenProvider

    overridden = QwenProvider(
        ProviderConfig(
            provider_id="qwen",
            api_endpoint="https://example.invalid/compatible-mode/v1",
            credential_env="TEST_QWEN_API_KEY",
            default_model="qwen-custom",
        ),
        transport=transport,
        credential_resolver=lambda name: "test-key",
        model_catalog=custom,
    )
    caps = overridden.capabilities()
    assert caps.supports_reasoning_budget is True
    assert overridden.model_info().context_window is None


def test_capability_matrix() -> None:
    """Effective capability matrix for the documented Qwen line-up.

    Only facts verified against official docs are asserted. ``structured`` is
    the non-thinking-mode value (``capabilities()`` defaults thinking OFF for
    hybrid models, FORCED for thinking-only models).
    """
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    matrix = {
        # model: (thinking, budget, preserve_thinking, structured, tool_calling)
        "qwen3.8-max-preview": (True, True, True, False, True),
        "qwen3.7-max": (True, True, True, True, True),
        "qwen3.7-plus": (True, True, True, True, True),
        "qwen3.6-plus": (True, True, False, True, True),
        "qwen3.6-flash": (True, True, False, True, True),
        "qwen3.5-plus": (True, True, False, True, True),
        "qwen3.5-flash": (True, True, False, True, True),
        "qwen3-max": (True, True, False, True, True),
    }
    for model, (thinking, budget, preserve, structured, tools) in matrix.items():
        caps = provider.capabilities(model)
        assert caps.supports_reasoning is thinking, model
        assert caps.supports_reasoning_budget is budget, model
        assert caps.supports_preserved_thinking is preserve, model
        assert caps.supports_structured_output is structured, model
        assert caps.supports_tool_calling is tools, model
        assert caps.supports_streaming is True, model
