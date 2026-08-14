"""Configuration model contracts."""

from __future__ import annotations

from qwen_research.common.serialization import dumps, loads
from qwen_research.config import Config, PathsConfig, SecurityConfig


def test_default_config() -> None:
    config = Config()
    assert config.system.name == "qwen-research"
    assert config.security.local_only is True
    assert config.security.allow_write is False


def test_config_roundtrip() -> None:
    config = Config(security=SecurityConfig(allow_write=True), paths=PathsConfig(corpus="c"))
    restored = loads(dumps(config))
    assert restored == config
