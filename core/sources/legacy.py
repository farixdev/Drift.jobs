"""Wrap the legacy first-party scrapers (core/scraper/) as SourceDefinitions.

Lets the Phase-7 engine run them through the same pool / priority / circuit-breaker
/ streaming path as the declarative ATS sources — without rewriting each scraper.
They execute via `run_legacy` (the scraper does its own HTTP), so query_mapper /
response_parser aren't used. As Phase 6 Tiers 2-6 convert these to true
declarative definitions, entries drop off this list.
"""
from __future__ import annotations

from core.sources.spec import SourceDefinition

# slug -> (display_name, adapter_type priority-hint, rate_limit_rpm)
_LEGACY = {
    "jobicy":    ("Jobicy", "api", 60),
    "themuse":   ("The Muse", "api", 60),
    "arbeitnow": ("Arbeitnow", "api", 60),
    "remoteok":  ("RemoteOK", "api", 60),
    "remotive":  ("Remotive", "api", 60),
    "hn":        ("Hacker News", "rss", 60),
    "wwr":       ("We Work Remotely", "search_engine", 30),
}


def _make(slug, name, adapter_type, rpm) -> SourceDefinition:
    return SourceDefinition(
        slug=slug, display_name=name, category="feed", adapter_type=adapter_type,
        base_url="", auth_type="none", auth_env_key="", rate_limit_rpm=rpm,
        concurrency_limit=1, robots_check=False,
        query_mapper=lambda c: [], response_parser=lambda r, s: [],
        legacy_slug=slug, note="Legacy first-party feed.")


LEGACY_DEFINITIONS: dict[str, SourceDefinition] = {
    slug: _make(slug, name, atype, rpm) for slug, (name, atype, rpm) in _LEGACY.items()
}
