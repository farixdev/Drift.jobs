"""Declarative source system — the value types.

A source is data, not code: a `SourceDefinition` names its endpoints and supplies
two pure functions — `query_mapper(criteria) -> [RequestSpec]` and
`response_parser(raw, spec) -> [RawJob]`. The engine (`runner.py`) knows nothing
about any specific board; adding a source means dropping a definition into
`core/sources/definitions/`, never touching engine code.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Callable

# Reuse the existing canonical raw type so downstream scoring is unchanged.
from core.scraper.base import RawJob  # noqa: F401  (re-exported)


@dataclass
class SearchCriteria:
    """The full, saveable, reusable query object (Phase 5).

    Every field is optional except role terms. The legacy `keywords`/`location`/
    `remote`/`companies` fields are retained so existing callers keep working;
    `effective_keywords()` unifies the role terms for source-level filtering.
    """
    # -- Role (only truly required group) --------------------------------- #
    titles: list[str] = field(default_factory=list)
    include_variants: bool = True
    keywords_required: list[str] = field(default_factory=list)
    keywords_nice: list[str] = field(default_factory=list)
    keywords_excluded: list[str] = field(default_factory=list)
    seniority: list[str] = field(default_factory=list)     # controlled vocab
    boolean_query: str = ""                                # power-user override

    # -- Location --------------------------------------------------------- #
    location_mode: str = "any"                             # remote|hybrid|onsite|any
    cities: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    radius_km: int | None = None
    radius_point: str = ""
    remote_in_country: str = ""
    remote_tz_offset: int | None = None
    relocation_ok: bool = False

    # -- Compensation ----------------------------------------------------- #
    salary_min: int | None = None
    salary_currency: str = "USD"
    salary_period: str = "year"
    include_unstated_salary: bool = True
    equity_required: bool = False

    # -- Employment ------------------------------------------------------- #
    employment_types: list[str] = field(default_factory=list)  # full_time, contract, …

    # -- Company ---------------------------------------------------------- #
    company_sizes: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    funding_stages: list[str] = field(default_factory=list)
    exclude_companies: list[str] = field(default_factory=list)
    only_companies: list[str] = field(default_factory=list)
    exclude_staffing: bool = False
    exclude_domains: list[str] = field(default_factory=list)

    # -- Eligibility ------------------------------------------------------ #
    visa_sponsorship: bool = False
    security_clearance: str = "any"                        # any|required|none

    # -- Freshness -------------------------------------------------------- #
    posted_within_days: int | None = None                 # 1,3,7,14,30; None=any

    # -- Volume ----------------------------------------------------------- #
    min_results: int = 0
    max_results: int = 0
    max_per_source: int = 60
    max_per_company: int = 0

    # -- Sources ---------------------------------------------------------- #
    sources: list[str] = field(default_factory=list)      # enabled keys; []=defaults
    source_categories: list[str] = field(default_factory=list)

    # -- Legacy / engine compat ------------------------------------------ #
    keywords: list[str] = field(default_factory=list)     # used by from_legacy
    location: str = ""
    remote: bool | None = None
    companies: list[str] | None = None                    # ATS board override

    # -- helpers ---------------------------------------------------------- #
    def effective_keywords(self) -> list[str]:
        """Role terms used for source-level keyword matching."""
        terms = list(self.titles) + list(self.keywords_required) + \
            list(self.keywords_nice) + list(self.keywords)
        return list(dict.fromkeys(t for t in terms if t))

    def board_override(self) -> list[str] | None:
        return self.only_companies or self.companies or None

    @classmethod
    def from_legacy(cls, keywords: list[str], location: str) -> "SearchCriteria":
        return cls(keywords=list(keywords or []), location=location or "",
                   keywords_required=list(keywords or []))

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SearchCriteria":
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in valid})


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
    # When set, this source is a legacy BaseScraper (core/scraper/) run via
    # run_legacy() rather than the declarative query_mapper/response_parser path.
    legacy_slug: str = ""


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
