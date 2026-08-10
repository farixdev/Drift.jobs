"""Provider factory — build the right LLMProvider for a slug."""
from __future__ import annotations

from functools import lru_cache

from core.ai.base import LLMProvider
from core.ai.keystore import KeyStore
from core.ai.native import AnthropicProvider, GeminiProvider
from core.ai.openai_compat import OpenAICompatProvider
from core.ai.registry import get_spec

_BY_KIND = {
    "openai_compat": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


def build_provider(slug: str, keystore: KeyStore | None = None) -> LLMProvider:
    spec = get_spec(slug)
    cls = _BY_KIND[spec.kind]
    return cls(spec, keystore=keystore)


@lru_cache(maxsize=None)
def _cached(slug: str) -> LLMProvider:
    return build_provider(slug)


def get_provider(slug: str) -> LLMProvider:
    """Process-cached provider using the default keystore."""
    return _cached(slug)


def reset_providers() -> None:
    _cached.cache_clear()
