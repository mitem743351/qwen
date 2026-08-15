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

Facts encoded here (and their sources):

- **thinking** — the model supports ``enable_thinking`` (hybrid) or always
  thinks (thinking-only). Qwen2.5-era chat models are hybrid; ``qwq-*`` are
  thinking-only.
- **thinking_budget** — the model accepts a numeric ``thinking_budget`` token
  cap. Per the QwenCloud "Thinking" guide this is supported by all
  thinking-capable models *from Qwen3 onward* (plus GLM/Kimi); it is **not**
  available on the Qwen2.5-era ``qwen-max``/``qwen-plus``/``qwen-turbo``
  hybrid models.
- **context_window** — the known context length (tokens), ``None`` where the
  value is not documented reliably here.
- **max_output_tokens** — the known output-token ceiling, ``None`` where
  unknown (negotiation then accepts the requested value without a bound).

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


def _m(
    model: str,
    *,
    context: int | None = None,
    max_out: int | None = None,
    thinking: bool = False,
    thinking_budget: bool = False,
) -> QwenModelSpec:
    return QwenModelSpec(
        model=model,
        context_window=context,
        max_output_tokens=max_out,
        thinking=thinking,
        thinking_budget=thinking_budget,
    )


#: Current Qwen model line-up (snapshot of the 2026 DashScope catalog).
QWEN_MODELS: tuple[QwenModelSpec, ...] = (
    # Qwen3.x flagships — native thinking + numeric thinking_budget.
    _m("qwen3.8-max", context=1_000_000, thinking=True, thinking_budget=True),
    _m("qwen3.7-max", context=1_000_000, thinking=True, thinking_budget=True),
    _m("qwen3.7-plus", context=1_000_000, thinking=True, thinking_budget=True),
    _m("qwen3.6-plus", thinking=True, thinking_budget=True),
    _m("qwen3.6-flash", thinking=True, thinking_budget=True),
    _m("qwen3.6", thinking=True, thinking_budget=True),
    _m("qwen3.5-plus", thinking=True, thinking_budget=True),
    _m("qwen3.5", thinking=True, thinking_budget=True),
    _m("qwen3-max", context=131_072, thinking=True, thinking_budget=True),
    _m("qwen3-next", thinking=True, thinking_budget=True),
    # Qwen3-era consumer aliases (hybrid thinking).
    _m("qwen-plus", context=131_072, thinking=True),
    _m("qwen-flash", thinking=True),
    # Qwen2.5-era chat models — hybrid thinking, no numeric thinking_budget.
    _m("qwen-max", context=32_768, thinking=True),
    _m("qwen-turbo", context=131_072),
    # Reasoning-only research models.
    _m("qwq-plus", context=131_072, thinking=True, thinking_budget=True),
    _m("qwq-32b", context=131_072, thinking=True, thinking_budget=True),
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
