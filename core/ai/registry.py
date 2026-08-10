"""Provider registry — the single source of truth for where each provider lives.

`base_url` and `host` are used to build requests AND to enforce the host-match
assertion before every call: a key only ever transits to its own provider's
registered host (Phase 3 key-safety rule). Every entry's endpoint was probed
live on `VERIFIED` below; see docs/AI_PROVIDERS.md for the raw results.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

VERIFIED = "2026-08-10"  # date the endpoints in this file were last probed live


@dataclass(frozen=True)
class ProviderSpec:
    slug: str
    display_name: str
    kind: str                 # "openai_compat" | "anthropic" | "gemini"
    base_url: str             # no trailing slash
    models_path: str          # relative path to the model-listing endpoint
    needs_key: bool
    env_key: str              # legacy .env variable, migrated into the keystore
    auth_style: str           # "bearer" | "x-api-key" | "x-goog-api-key" | "none"
    supports_embeddings: bool
    notes: str = ""

    @property
    def host(self) -> str:
        return urlparse(self.base_url).netloc.lower()

    @property
    def models_url(self) -> str:
        return f"{self.base_url}{self.models_path}"


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        "anthropic", "Anthropic", "anthropic",
        "https://api.anthropic.com/v1", "/models",
        needs_key=True, env_key="ANTHROPIC_API_KEY", auth_style="x-api-key",
        supports_embeddings=False, notes="Native Messages API."),
    "openai": ProviderSpec(
        "openai", "OpenAI", "openai_compat",
        "https://api.openai.com/v1", "/models",
        needs_key=True, env_key="OPENAI_API_KEY", auth_style="bearer",
        supports_embeddings=True),
    "gemini": ProviderSpec(
        "gemini", "Google Gemini", "gemini",
        "https://generativelanguage.googleapis.com/v1beta", "/models",
        needs_key=True, env_key="GEMINI_API_KEY", auth_style="x-goog-api-key",
        supports_embeddings=True, notes="Native generateContent API."),
    "groq": ProviderSpec(
        "groq", "Groq", "openai_compat",
        "https://api.groq.com/openai/v1", "/models",
        needs_key=True, env_key="GROQ_API_KEY", auth_style="bearer",
        supports_embeddings=False, notes="OpenAI-compatible."),
    "openrouter": ProviderSpec(
        "openrouter", "OpenRouter", "openai_compat",
        "https://openrouter.ai/api/v1", "/models",
        needs_key=True, env_key="OPENROUTER_API_KEY", auth_style="bearer",
        supports_embeddings=False, notes="OpenAI-compatible, multi-model. Public model list."),
    "mistral": ProviderSpec(
        "mistral", "Mistral", "openai_compat",
        "https://api.mistral.ai/v1", "/models",
        needs_key=True, env_key="MISTRAL_API_KEY", auth_style="bearer",
        supports_embeddings=True),
    "deepseek": ProviderSpec(
        "deepseek", "DeepSeek", "openai_compat",
        "https://api.deepseek.com/v1", "/models",
        needs_key=True, env_key="DEEPSEEK_API_KEY", auth_style="bearer",
        supports_embeddings=False),
    "ollama": ProviderSpec(
        "ollama", "Ollama (local)", "openai_compat",
        "http://localhost:11434/v1", "/models",
        needs_key=False, env_key="", auth_style="none",
        supports_embeddings=True, notes="Local, no key. Offline path."),
}


def get_spec(slug: str) -> ProviderSpec:
    try:
        return PROVIDERS[slug]
    except KeyError:
        raise KeyError(f"Unknown provider: {slug!r}") from None
