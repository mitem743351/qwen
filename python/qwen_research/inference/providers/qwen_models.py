"""Qwen model catalog (2026 contract).

A static, model-specific table of what each Qwen model id actually supports.
This is the single source of truth the :class:`QwenProvider` consults to turn a
model id into ``ProviderCapabilities`` / ``ProviderLimits`` / ``ModelInfo`` —
so capability discovery is **per model**, not a single blanket for the whole
family.

The table is a best-effort snapshot of the current DashScope line-up and is
**operator-overridable**: ``QwenProvider`` accepts a ``model_catalog`` mapping,
so a deployment can pin its own models and bounds. Unknown model ids resolve to
a conservative spec (no reasoning, no reasoning budget, unknown context) rather
than assuming a capability that may not exist.

Facts encoded here (and their official sources, verified 2026-08):

- **thinking** — the model supports ``enable_thinking`` (hybrid) or always
  thinks (thinking-only, ``thinking_always_enabled``). Qwen3.x models are
  hybrid; ``qwq-*`` and ``qwen3.8-max-preview`` always think.
- **thinking_budget** — a numeric token cap on thinking. Supported by Qwen3
  thinking models (and the Qwen3-era ``qwen-plus`` alias); **not** available on
  the Qwen2.5-era ``qwen-max``/``qwen-turbo`` or the Qwen2.5-based ``qwq-*``.
- **preserve_thinking** — passes prior-turn ``reasoning_content`` forward in
  multi-turn conversations. Supported **only** by ``qwen3.7-max`` /
  ``qwen3.7-plus`` (and their dated snapshots) and ``qwen3.8-max-preview``
  (Token Plan).
- **structured_output** — ``response_format=json_object``. Available on hybrid
  models in non-thinking mode; **not** available in thinking mode and therefore
  not available at all on thinking-only models (``qwq-*``,
  ``qwen3.8-max-preview``).
- **tool_calling** — native function calling (application-defined tools).
- **builtin tools** — provider-hosted tools (web search, code interpreter, web
  scraping) documented only for ``qwen3.8-max-preview`` under Token Plan. These
  are cataloged, never invoked (execution is a later phase).
- **reasoning_effort** — explicit reasoning-depth levels (``low``/``medium``/
  ``xhigh``) documented for ``qwen3.8-max-preview`` on the Token Plan endpoint.
  **Cataloged but NOT yet executed**: the adapter records the capability in
  ``reasoning_effort_levels`` but never emits ``reasoning_effort`` (its
  composition with the XHIGH workflow is Phase 10).
- **lifecycle / availability / plans** — ``GA``/``PUBLIC`` for the standard
  line-up; ``PREVIEW``/``PLAN_RESTRICTED``/``TOKEN_PLAN`` for
  ``qwen3.8-max-preview``.

Maintenance: this table is a **snapshot**, not a live query. When the Qwen
line-up changes, re-verify each fact against the official QwenCloud / Alibaba
Model Studio model pages and update this table (and the corresponding tests in
``tests/inference/test_qwen_models.py``). Prefer leaving a field ``False``/
``None`` (conservative) over asserting a capability that has not been confirmed
against official docs. Do **not** infer new-model capabilities by copying a
previous model's spec unless that approximation is explicitly recorded.

Authoritative sources (official docs, not third-party):

- QwenCloud "Thinking": https://docs.qwencloud.com/developer-guides/text-generation/thinking
- QwenCloud "Structured output": https://docs.qwencloud.com/developer-guides/text-generation/structured-output
- QwenCloud "Qwen Code" (Token Plan): https://docs.qwencloud.com/developer-guides/clients-and-developer-tools/qwen-code
- Model Studio "Use deep thinking models via API": https://www.alibabacloud.com/help/en/model-studio/deep-thinking
- Model Studio "Qwen API via DashScope": https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-dashscope

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
)


class QwenApiSurface(StrEnum):
    """Qwen API surfaces. Chat Completions and Responses differ in features."""

    OPENAI_COMPATIBLE_CHAT = "openai_compatible_chat"
    OPENAI_COMPATIBLE_RESPONSES = "openai_compatible_responses"
    DASHSCOPE = "dashscope"
    TOKEN_PLAN = "token_plan"
    UNKNOWN = "unknown"


@serializable
@dataclasses.dataclass(frozen=True)
class QwenModelSpec:
    """Model-specific facts the Qwen adapter needs to advertise capabilities.

    ``plans`` / ``regions`` / ``api_surfaces`` are **restriction lists**: empty
    means "no restriction", non-empty means "available only under those".
    """

    model: str
    aliases: tuple[str, ...] = ()
    lifecycle: ModelLifecycle = ModelLifecycle.GA
    availability: ModelAvailability = ModelAvailability.PUBLIC
    plans: tuple[AvailabilityPlan, ...] = ()
    regions: tuple[str, ...] = ()
    api_surfaces: tuple[QwenApiSurface, ...] = ()

    context_window: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_thinking_tokens: int | None = None

    thinking: bool = False
    thinking_always_enabled: bool = False
    thinking_budget: bool = False
    preserve_thinking: bool = False
    reasoning_effort_levels: tuple[str, ...] = ()

    structured_output: bool = True
    tool_calling: bool = True
    parallel_tool_calling: bool = False
    streaming: bool = True
    context_caching: bool = False

    builtin_web_search: bool = False
    builtin_code_interpreter: bool = False
    builtin_web_scraping: bool = False

    notes: str = ""
    source_urls: tuple[str, ...] = ()


def _m(
    model: str,
    *,
    context: int | None = None,
    max_out: int | None = None,
    thinking: bool = False,
    thinking_budget: bool = False,
    preserve_thinking: bool = False,
    structured_output: bool = True,
    tool_calling: bool = True,
    streaming: bool = True,
    lifecycle: ModelLifecycle = ModelLifecycle.GA,
    availability: ModelAvailability = ModelAvailability.PUBLIC,
    plans: tuple[AvailabilityPlan, ...] = (),
) -> QwenModelSpec:
    return QwenModelSpec(
        model=model,
        context_window=context,
        max_output_tokens=max_out,
        thinking=thinking,
        thinking_budget=thinking_budget,
        preserve_thinking=preserve_thinking,
        structured_output=structured_output,
        tool_calling=tool_calling,
        streaming=streaming,
        lifecycle=lifecycle,
        availability=availability,
        plans=plans,
    )


#: Current Qwen model line-up (snapshot of the 2026 DashScope catalog).
QWEN_MODELS: tuple[QwenModelSpec, ...] = (
    # Qwen3.x flagships — native thinking + numeric thinking_budget.
    _m(
        "qwen3.7-max",
        context=1_000_000,
        max_out=65_536,
        thinking=True,
        thinking_budget=True,
        preserve_thinking=True,
    ),
    _m(
        "qwen3.7-plus",
        context=1_000_000,
        thinking=True,
        thinking_budget=True,
        preserve_thinking=True,
    ),
    _m("qwen3.6-plus", thinking=True, thinking_budget=True),
    _m("qwen3.6-flash", thinking=True, thinking_budget=True),
    _m("qwen3.6", thinking=True, thinking_budget=True),
    _m("qwen3.5-plus", thinking=True, thinking_budget=True),
    _m("qwen3.5-flash", thinking=True, thinking_budget=True),
    _m("qwen3.5", thinking=True, thinking_budget=True),
    _m("qwen3-max", context=131_072, thinking=True, thinking_budget=True),
    _m("qwen3-next", thinking=True, thinking_budget=True),
    # Qwen3-era consumer aliases (hybrid thinking + numeric budget).
    _m("qwen-plus", context=131_072, thinking=True, thinking_budget=True),
    _m("qwen-flash", thinking=True),
    # Qwen2.5-era chat models — hybrid thinking, no numeric thinking_budget.
    _m("qwen-max", context=32_768, thinking=True),
    _m("qwen-turbo", context=131_072),
    # Reasoning-only research models (thinking-only: no structured output/tools).
    _m(
        "qwq-plus",
        context=131_072,
        thinking=True,
        structured_output=False,
        tool_calling=False,
    ),
    _m(
        "qwq-32b",
        context=131_072,
        thinking=True,
        structured_output=False,
        tool_calling=False,
    ),
    # Official QwenCloud preview model — Token Plan only.
    QwenModelSpec(
        model="qwen3.8-max-preview",
        lifecycle=ModelLifecycle.PREVIEW,
        availability=ModelAvailability.PLAN_RESTRICTED,
        plans=(AvailabilityPlan.TOKEN_PLAN,),
        api_surfaces=(QwenApiSurface.OPENAI_COMPATIBLE_CHAT, QwenApiSurface.TOKEN_PLAN),
        context_window=983_616,
        max_output_tokens=131_072,
        thinking=True,
        thinking_always_enabled=True,
        thinking_budget=True,
        preserve_thinking=True,
        reasoning_effort_levels=("low", "medium", "xhigh"),
        structured_output=False,  # always-on thinking → no structured output
        tool_calling=True,
        streaming=True,
        builtin_web_search=True,
        builtin_code_interpreter=True,
        builtin_web_scraping=True,
        notes=(
            "Official QwenCloud preview; Token Plan only; thinking always "
            "enabled; reasoning_effort low/medium/xhigh (cataloged, not yet "
            "executed). Context 983,616 tokens. Structured output is not "
            "available on the preview endpoint."
        ),
        source_urls=(
            "https://docs.qwencloud.com/developer-guides/clients-and-developer-tools/qwen-code",
            "https://docs.qwencloud.com/developer-guides/text-generation/thinking",
        ),
    ),
)

#: Fast lookup from model id to spec.
QWEN_MODEL_TABLE: dict[str, QwenModelSpec] = {s.model: s for s in QWEN_MODELS}


def resolve_spec(model: str, catalog: dict[str, QwenModelSpec] | None = None) -> QwenModelSpec:
    """Resolve *model* to a spec, falling back to a conservative unknown spec.

    Unknown models are **not** rejected here (the API itself reports model
    existence via ``ModelNotFoundError``); they simply advertise no reasoning
    capability and an unknown context so negotiation stays honest.
    """
    table = catalog if catalog is not None else QWEN_MODEL_TABLE
    return table.get(model, QwenModelSpec(model=model, lifecycle=ModelLifecycle.UNKNOWN,
                                          availability=ModelAvailability.UNKNOWN))
