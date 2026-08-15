"""Inference configuration (provider-neutral + Qwen-specific).

Credentials are referenced by environment-variable name (``credential_env``) —
never stored as values here. Qwen-specific fields stay in the Qwen config layer;
the generic ``InferencePolicy``/domain model is untouched.
"""

from __future__ import annotations

import dataclasses

from qwen_research.common.serialization import serializable


@serializable
@dataclasses.dataclass(frozen=True)
class RetryConfig:
    """Provider-level retry policy for known transient failures."""

    max_attempts: int = 2
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    #: Provider error statuses that are retryable (RateLimited/Retryable/Server).
    retryable_statuses: tuple[str, ...] = (
        "rate_limited",
        "retryable",
        "server_error",
    )


@serializable
@dataclasses.dataclass(frozen=True)
class TimeoutConfig:
    """Separate timeout limits for inference."""

    connection_seconds: float = 10.0
    request_seconds: float = 120.0
    stream_idle_seconds: float = 30.0


@serializable
@dataclasses.dataclass(frozen=True)
class ProviderConfig:
    """Generic provider configuration (no credential values).

    ``endpoint_profile`` / ``region`` / ``plan`` are optional context selectors
    that scope model availability and effective capabilities; when empty the
    provider falls back to its default endpoint profile / plan.
    """

    provider_id: str
    enabled: bool = True
    api_endpoint: str = ""
    credential_env: str = ""
    default_model: str = ""
    endpoint_profile: str = ""
    region: str = ""
    plan: str = ""
    timeout: TimeoutConfig = dataclasses.field(default_factory=TimeoutConfig)
    retry: RetryConfig = dataclasses.field(default_factory=RetryConfig)


@serializable
@dataclasses.dataclass(frozen=True)
class InferenceConfig:
    """Aggregate inference configuration."""

    default_provider: str = "qwen"
    default_model: str = ""
    timeout_seconds: float = 120.0
    providers: tuple[ProviderConfig, ...] = ()


#: A conservative, documented default Qwen provider configuration (no secrets).
DEFAULT_QWEN_PROVIDER = ProviderConfig(
    provider_id="qwen",
    enabled=True,
    # OpenAI-compatible international endpoint (see docs/setup/inference.md).
    api_endpoint="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    credential_env="DASHSCOPE_API_KEY",
    default_model="qwen3.7-max",
)
