"""Blending: user weights, freshness decay, and the blocklist filter."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone

_DEFAULT_WEIGHTS = {"lexical": 0.25, "semantic": 0.30, "llm": 0.45}
_HALF_LIFE_DAYS = 30
_FRESHNESS_FLOOR = 0.4


def weights() -> dict:
    try:
        from db import get_setting
        w = dict(_DEFAULT_WEIGHTS)
        w.update(get_setting("ranking.weights", {}) or {})
        return w
    except Exception:
        return dict(_DEFAULT_WEIGHTS)


def freshness_factor(posted_at_iso: str | None) -> float:
    """Exponential decay by age (half-life 30d), floored so old roles aren't zeroed.
    Unknown dates get a mild neutral factor rather than a penalty or a boost."""
    if not posted_at_iso:
        return 0.9
    try:
        dt = datetime.fromisoformat(posted_at_iso)
    except ValueError:
        return 0.9
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
    return max(_FRESHNESS_FLOOR, 0.5 ** (days / _HALF_LIFE_DAYS))


def load_blocklist() -> dict:
    try:
        from db.connection import connect
        with closing(connect()) as conn:
            rows = conn.execute("SELECT type, value FROM blocklist").fetchall()
    except Exception:
        return {}
    out: dict[str, set] = {}
    for r in rows:
        out.setdefault(r["type"], set()).add((r["value"] or "").strip().lower())
    return out


def is_blocked(job, bl: dict) -> bool:
    if not bl:
        return False
    from core.normalize.fields import company_key
    if company_key(job.company) in {company_key(c) for c in bl.get("company", set())}:
        return True
    hay = f"{job.title} {job.description}".lower()
    if any(kw and kw in hay for kw in bl.get("keyword", set())):
        return True
    if (job.source or "").lower() in bl.get("source", set()):
        return True
    url = (job.url or "").lower()
    if any(dom and dom in url for dom in bl.get("domain", set())):
        return True
    return False
