"""Per-task model routing with ordered fallback chains.

Each of the eight tasks maps to a primary (provider, model, temperature,
max_tokens) plus an ordered fallback chain the manager walks on provider failure.
Defaults target Groq — the provider this install already has a key for — so the
app keeps working out of the box; the user re-points any task from Settings, and
overrides persist in the `ai.routing` setting.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_ROUTING_KEY = "ai.routing"

# Canonical task list (Phase 3 spec). Order is display order.
TASKS = [
    "resume_parse", "keyword_extract", "query_expand", "job_rerank",
    "job_explain", "resume_tailor", "cover_letter", "embeddings",
]

TASK_LABELS = {
    "resume_parse": "Resume parsing",
    "keyword_extract": "Keyword extraction",
    "query_expand": "Query expansion",
    "job_rerank": "Job reranking",
    "job_explain": "Job explanations",
    "resume_tailor": "Resume tailoring",
    "cover_letter": "Cover letters",
    "embeddings": "Embeddings",
}


@dataclass
class Route:
    provider: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 1024
    fallback: list[dict] = field(default_factory=list)  # [{provider, model}, ...]

    def chain(self) -> list[tuple[str, str]]:
        """(provider, model) pairs, primary first then fallbacks."""
        out = [(self.provider, self.model)]
        for f in self.fallback:
            if f.get("provider") and f.get("model"):
                out.append((f["provider"], f["model"]))
        return out


_GROQ_FAST = "llama-3.1-8b-instant"
_GROQ_SHARP = "llama-3.3-70b-versatile"

DEFAULT_ROUTES: dict[str, Route] = {
    "resume_parse":    Route("groq", _GROQ_FAST, 0.1, 1200, [{"provider": "groq", "model": _GROQ_SHARP}]),
    "keyword_extract": Route("groq", _GROQ_FAST, 0.2, 600),
    "query_expand":    Route("groq", _GROQ_FAST, 0.3, 600),
    "job_rerank":      Route("groq", _GROQ_SHARP, 0.2, 2048, [{"provider": "groq", "model": _GROQ_FAST}]),
    "job_explain":     Route("groq", _GROQ_SHARP, 0.3, 1200),
    "resume_tailor":   Route("groq", _GROQ_SHARP, 0.4, 2048),
    "cover_letter":    Route("groq", _GROQ_SHARP, 0.6, 1200),
    # Embeddings: local-first (free, offline), OpenAI as the keyed fallback.
    "embeddings":      Route("ollama", "nomic-embed-text", 0.0, 0,
                             [{"provider": "openai", "model": "text-embedding-3-small"}]),
}


def get_route(task: str) -> Route:
    """Resolved route: default overlaid with any user override from settings."""
    base = DEFAULT_ROUTES.get(task)
    if base is None:
        raise KeyError(f"unknown task: {task!r}")
    try:
        from db import get_setting
        overrides = get_setting(_ROUTING_KEY, {}) or {}
    except Exception:
        overrides = {}
    o = overrides.get(task)
    if not o:
        return base
    return Route(
        provider=o.get("provider", base.provider),
        model=o.get("model", base.model),
        temperature=float(o.get("temperature", base.temperature)),
        max_tokens=int(o.get("max_tokens", base.max_tokens)),
        fallback=o.get("fallback", base.fallback),
    )


def set_route(task: str, provider: str, model: str, *, temperature: float | None = None,
              max_tokens: int | None = None, fallback: list[dict] | None = None) -> None:
    from db import get_setting, set_setting
    if task not in DEFAULT_ROUTES:
        raise KeyError(f"unknown task: {task!r}")
    overrides = get_setting(_ROUTING_KEY, {}) or {}
    base = DEFAULT_ROUTES[task]
    overrides[task] = {
        "provider": provider,
        "model": model,
        "temperature": base.temperature if temperature is None else temperature,
        "max_tokens": base.max_tokens if max_tokens is None else max_tokens,
        "fallback": base.fallback if fallback is None else fallback,
    }
    set_setting(_ROUTING_KEY, overrides)
