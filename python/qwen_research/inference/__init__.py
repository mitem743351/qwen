"""Inference Runtime contracts.

Only the provider-neutral ``InferenceProvider`` protocol lives here in
Phase 1. No Qwen API, local model, or network implementation exists.
"""

from qwen_research.inference.interfaces import InferenceProvider

__all__ = ["InferenceProvider"]
