"""Adapter layer: concrete implementations of the ports.

- ``mock``            offline scripted provider (tests, demos, CI)
- ``openai_compat``   one adapter for every OpenAI-shaped endpoint
- ``cache``           sqlite response cache + read-through wrapper
- ``snapshot_store``  YAML baseline persistence
"""

from promptdrift.adapters.cache import CachedProvider, SqliteCache
from promptdrift.adapters.mock import MockProvider
from promptdrift.adapters.openai_compat import OpenAICompatProvider
from promptdrift.domain.suite import BaseProviderConfig, MockConfig, OpenAICompatConfig
from promptdrift.errors import ProviderError
from promptdrift.ports import Provider

__all__ = [
    "CachedProvider",
    "MockProvider",
    "OpenAICompatProvider",
    "SqliteCache",
    "build_provider",
]


def build_provider(config: BaseProviderConfig) -> Provider:
    """Construct the provider adapter matching a suite's provider config."""
    if isinstance(config, MockConfig):
        return MockProvider(config)
    if isinstance(config, OpenAICompatConfig):
        return OpenAICompatProvider(config)
    raise ProviderError(f"no adapter registered for provider config {type(config).__name__}")
