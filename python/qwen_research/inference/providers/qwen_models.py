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
  thinks (thinking-only). Qwen3.x models are hybrid; ``qwq-*`` are
  thinking-only. Source: QwenCloud "Thinking" guide and Alibaba Model Studio
  "Use deep thinking models via API".
- **thinking_budget** — a numeric token cap on thinking. Supported by Qwen3
  thinking models (and the Qwen3-era ``qwen-plus`` alias); **not** available on
  the Qwen2.5-era ``qwen-max``/``qwen-turbo`` or the Qwen2.5-based ``qwq-*``.
  Source: Model Studio "Use deep thinking models via API".
- **preserve_thinking** — passes prior-turn ``reasoning_content`` forward in
  multi-turn conversations. Supported **only** by ``qwen3.7-max`` and
  ``qwen3.7-plus`` (and their dated snapshots). Source: QwenCloud "Thinking" →
  "Preserve thinking in multi-turn" and Model Studio "Use deep thinking models".
- **structured_output** — ``response_format=json_object``. Available on hybrid
  models in non-thinking mode; **not** available in thinking mode and therefore
  not available at all on thinking-only ``qwq-*`` models. Source: QwenCloud
  "Structured output".
- **tool_calling** — native function calling. Available on the chat models;
  **not** available on the thinking-only ``qwq-*`` reasoning models. Source:
  Model Studio API reference and QwenCloud "Thinking" (function calling with
  thinking mode).
- **streaming** — SSE output. Supported by all Qwen chat models (Qwen3
  open-source models in fact *require* streaming). Source: QwenCloud "Thinking".
- **context_window** — the known context length (tokens), ``None`` where the
  value is not documented reliably here.
- **max_output_tokens** — the known output-token ceiling, ``None`` where
  unknown (negotiation then accepts the requested value without a bound).

Maintenance: this table is a **snapshot**, not a live query. When the Qwen
line-up changes, re-verify each fact against the official QwenCloud / Alibaba
Model Studio model pages and update this table (and the corresponding tests in
``tests/inference/test_qwen_models.py``). Prefer leaving a field ``False``/
``None`` (conservative) over asserting a capability that has not been confirmed
against official docs.

No credentials and no hidden chain-of-thought live here.
"""

from __future__ import annotations

import dataclasses

from qwen_research.common.serialization import serializable


@serializable
@dataclasses.dataclass(frozen=True)
class QwenModelSpec:
    """Model-specific facts the Qwen adapter needs to advertise capabilities."""

    model: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    thinking: bool = False
    thinking_budget: bool = False
    preserve_thinking: bool = False
    structured_output: bool = True
    tool_calling: bool = True
    streaming: bool = True


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
    return table.get(model, QwenModelSpec(model=model))
