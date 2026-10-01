"""Tests for the provider factory."""

from __future__ import annotations

import pytest

from promptdrift.adapters import build_provider
from promptdrift.adapters.mock import MockProvider
from promptdrift.adapters.openai_compat import OpenAICompatProvider
from promptdrift.domain.suite import MockConfig, OpenAICompatConfig
from promptdrift.errors import ProviderError


def test_builds_mock() -> None:
    assert isinstance(build_provider(MockConfig()), MockProvider)


def test_builds_openai_compat() -> None:
    config = OpenAICompatConfig(model="m", base_url="https://x/v1", api_key_env="K")
    assert isinstance(build_provider(config), OpenAICompatProvider)


def test_unknown_config_raises() -> None:
    class MysteryConfig:
        pass

    with pytest.raises(ProviderError, match="no adapter registered"):
        build_provider(MysteryConfig())  # type: ignore[arg-type]
