"""Cost meter — usage → dollars, plus per task/run/day/provider aggregation.

Prices are USD per 1,000,000 tokens (input, output). The DEFAULT_PRICES below
are **rough estimates, not verified quotes** — the spec forbids hardcoding prices
we cannot verify, so they are seeds the user edits. Overrides live in the
`setting` table under `ai.pricing`, and `pricing_is_estimate()` tells the UI to
flag any provider still on defaults.
"""
from __future__ import annotations

from core.ai.types import Usage

_PRICING_KEY = "ai.pricing"

# provider -> { "default": [in, out], "<model-substring>": [in, out] }
# USD per 1M tokens. ESTIMATES — surfaced as editable + flagged in the UI.
DEFAULT_PRICES: dict[str, dict[str, list[float]]] = {
    "openai":     {"default": [2.5, 10.0], "mini": [0.15, 0.60],
                   "text-embedding-3-small": [0.02, 0.0],
                   "text-embedding-3-large": [0.13, 0.0]},
    "anthropic":  {"default": [3.0, 15.0], "haiku": [0.80, 4.0], "opus": [15.0, 75.0]},
    "gemini":     {"default": [1.25, 5.0], "flash": [0.15, 0.60]},
    "groq":       {"default": [0.20, 0.20], "70b": [0.59, 0.79], "8b": [0.05, 0.08]},
    "openrouter": {"default": [2.0, 6.0]},
    "mistral":    {"default": [2.0, 6.0], "small": [0.20, 0.60]},
    "deepseek":   {"default": [0.27, 1.10]},
    "ollama":     {"default": [0.0, 0.0]},  # local: no marginal cost
}


def _prices() -> dict:
    """Defaults overlaid with any user overrides from settings."""
    try:
        from db import get_setting
        overrides = get_setting(_PRICING_KEY, {}) or {}
    except Exception:
        overrides = {}
    merged = {p: dict(m) for p, m in DEFAULT_PRICES.items()}
    for provider, table in overrides.items():
        merged.setdefault(provider, {})
        merged[provider].update(table)
    return merged


def _rate(provider: str, model: str, prices: dict) -> list[float]:
    table = prices.get(provider) or {}
    best: list[float] | None = None
    best_len = -1
    model_l = (model or "").lower()
    for key, rate in table.items():
        if key == "default":
            continue
        if key.lower() in model_l and len(key) > best_len:
            best, best_len = rate, len(key)
    if best is not None:
        return best
    return table.get("default", [0.0, 0.0])


def estimate_cost(provider: str, model: str, usage: Usage) -> float:
    """USD for one call, from token counts and the (editable) price table."""
    rate_in, rate_out = _rate(provider, model, _prices())
    return (usage.prompt_tokens / 1_000_000) * rate_in + \
           (usage.completion_tokens / 1_000_000) * rate_out


def pricing_is_estimate(provider: str) -> bool:
    """True when the provider is still on default (unverified) prices."""
    try:
        from db import get_setting
        overrides = get_setting(_PRICING_KEY, {}) or {}
    except Exception:
        overrides = {}
    return provider not in overrides


def set_price(provider: str, model_key: str, rate_in: float, rate_out: float) -> None:
    from db import get_setting, set_setting
    overrides = get_setting(_PRICING_KEY, {}) or {}
    overrides.setdefault(provider, {})[model_key] = [float(rate_in), float(rate_out)]
    set_setting(_PRICING_KEY, overrides)


# --------------------------------------------------------------------------- #
# Usage ledger + aggregation (reads/writes llm_usage)
# --------------------------------------------------------------------------- #
def record_usage(*, task: str, provider: str, model: str, usage: Usage,
                 cost_usd: float, from_cache: bool = False, ok: bool = True,
                 error_class: str = "", fallback_depth: int = 0,
                 run_id: int | None = None) -> None:
    from contextlib import closing
    from db.connection import connect
    with closing(connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO llm_usage
                (run_id, task, provider, model, prompt_tokens, completion_tokens,
                 cost_usd, from_cache, ok, error_class, fallback_depth)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, task, provider, model, usage.prompt_tokens, usage.completion_tokens,
             cost_usd, int(from_cache), int(ok), error_class, fallback_depth),
        )


def spend_summary(scope: str = "day") -> dict:
    """Aggregate spend. scope in {'day','month','all'}. Returns totals + breakdown
    by provider and by task."""
    from contextlib import closing
    from db.connection import connect

    where = {
        "day": "WHERE ts >= datetime('now','start of day')",
        "month": "WHERE ts >= datetime('now','start of month')",
        "all": "",
    }.get(scope, "")
    with closing(connect()) as conn:
        total = conn.execute(
            f"SELECT COALESCE(SUM(cost_usd),0) c, COALESCE(SUM(prompt_tokens),0) pin, "
            f"COALESCE(SUM(completion_tokens),0) pout FROM llm_usage {where}"
        ).fetchone()
        by_provider = conn.execute(
            f"SELECT provider, COALESCE(SUM(cost_usd),0) c FROM llm_usage {where} "
            f"GROUP BY provider ORDER BY c DESC"
        ).fetchall()
        by_task = conn.execute(
            f"SELECT task, COALESCE(SUM(cost_usd),0) c FROM llm_usage {where} "
            f"GROUP BY task ORDER BY c DESC"
        ).fetchall()
    return {
        "scope": scope,
        "cost_usd": round(total["c"], 6),
        "prompt_tokens": total["pin"],
        "completion_tokens": total["pout"],
        "by_provider": {r["provider"]: round(r["c"], 6) for r in by_provider},
        "by_task": {r["task"]: round(r["c"], 6) for r in by_task},
    }
