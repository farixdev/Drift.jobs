"""Declarative source system — the value types.

A source is data, not code: a `SourceDefinition` names its endpoints and supplies
two pure functions — `query_mapper(criteria) -> [RequestSpec]` and
`response_parser(raw, spec) -> [RawJob]`. The engine (`runner.py`) knows nothing
about any specific board; adding a source means dropping a definition into
`core/sources/definitions/`, never touching engine code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# Reuse the existing canonical raw type so downstream scoring is unchanged.
from core.scraper.base import RawJob  # noqa: F401  (re-exported)


@dataclass
class SearchCriteria:
    """Minimal criteria for Tier 1. Phase 5 replaces this with the full builder;
    the field names here are a forward-compatible subset."""
    keywords: list[str] = field(default_factory=list)
    location: str = ""
    remote: bool | None = None
    max_per_source: int = 60
    # Optional explicit board/company override (Phase 5 'only_companies').
    companies: list[str] | None = None

    @classmethod
    def from_legacy(cls, keywords: list[str], location: str) -> "SearchCriteria":
        return cls(keywords=list(keywords or []), location=location or "")


@dataclass
class RequestSpec:
    url: str
    method: str = "GET"
    headers: dict | None = None
    params: dict | None = None
    json_body: dict | None = None
    meta: dict = field(default_factory=dict)  # e.g. {"company": "gitlab"}


@dataclass
class SourceDefinition:
    slug: str
    display_name: str
    category: str            # "ats" | "board" | "community" | ...
    adapter_type: str        # "api" | "rss" | "browser" | "search_engine"
    base_url: str
    auth_type: str           # "none" | "key"
    auth_env_key: str
    rate_limit_rpm: int
    concurrency_limit: int
    robots_check: bool
    query_mapper: Callable[[SearchCriteria], list[RequestSpec]]
    response_parser: Callable[[Any, RequestSpec], list[RawJob]]
    pagination: str = "none"  # "none" | "page" | "cursor"
    max_pages: int = 1
    enabled: bool = True
    health_check: Callable[[], bool] | None = None
    note: str = ""


@dataclass
class SourceResult:
    """Outcome of running one source — carries the diagnostics the UI must show
    (HTTP status, error class, timestamp): no silent failures (Prime Directive 3)."""
    slug: str
    status: str              # "done" | "failed" | "blocked" | "skipped"
    jobs: list = field(default_factory=list)
    http_status: int | None = None
    error_class: str = ""
    error_detail: str = ""
    duration_ms: int = 0
    boards_attempted: int = 0
    boards_succeeded: int = 0
    finished_at: str = ""
