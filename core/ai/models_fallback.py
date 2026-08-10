"""Maintained fallback model lists — used ONLY when a live /models fetch fails.

Runtime behaviour (see manager/providers): each provider's real model list is
fetched from its /models endpoint with the user's key and cached 24h. These
constants are the offline/failure fallback, never the primary source, so a
provider shipping new models still works the moment the user's key can reach it.

`LAST_VERIFIED` is the date these seeds were last checked. Entries marked
`# live` were fetched from the provider on that date; `# documented` are
well-known stable IDs used only as seeds until a live fetch supersedes them.
Do not treat `documented` IDs as guaranteed-current — that's what the live
fetch is for.
"""
from __future__ import annotations

LAST_VERIFIED = "2026-08-10"

MODELS_FALLBACK: dict[str, list[str]] = {
    # live — fetched from Groq /models on LAST_VERIFIED with the user's key
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-safeguard-20b",
        "qwen/qwen3.6-27b",
        "allam-2-7b",
        "groq/compound",
        "groq/compound-mini",
    ],
    # live — sample from OpenRouter public /models on LAST_VERIFIED (399 total)
    "openrouter": [
        "anthropic/claude-opus-5",
        "anthropic/claude-opus-5-fast",
        "deepseek/deepseek-v4-flash-latest",
        "qwen/qwen3.8-max",
    ],
    # documented — Anthropic model IDs (stable families)
    "anthropic": [
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-4-5-20251001",
    ],
    # documented — seeds only; live fetch supersedes
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "text-embedding-3-small",
        "text-embedding-3-large",
    ],
    "gemini": [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "text-embedding-004",
    ],
    "mistral": [
        "mistral-large-latest",
        "mistral-small-latest",
        "mistral-embed",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
    ],
    # documented — depends on what the user has pulled locally
    "ollama": [
        "llama3.1",
        "nomic-embed-text",
    ],
}


def fallback_models(slug: str) -> list[str]:
    return list(MODELS_FALLBACK.get(slug, []))
