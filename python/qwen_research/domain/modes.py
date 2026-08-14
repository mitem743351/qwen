"""Operating modes (inference ownership)."""

from __future__ import annotations

from enum import StrEnum


class OperatingMode(StrEnum):
    """Who owns the model inference loop for a given session/task.

    Defined in Phase 0.5 (see ``docs/architecture/operating-modes.md``). This
    is a domain-level fact, not a provider parameter.
    """

    STUDIO_NATIVE = "studio_native"
    GATEWAY_INFERENCE = "gateway_inference"
    HYBRID = "hybrid"
