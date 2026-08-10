"""Workable job boards — public, key-free, employer-canonical.

API: https://apply.workable.com/api/v1/widget/accounts/{token}?details=true
Returns the account name plus a `jobs` array with HTML `description`, a
`telecommuting` remote flag, and city/state/country. robots.txt allows our UA
(verified 2026-08-10).
"""
from __future__ import annotations

from core.scraper.util import human_date, strip_html
from core.sources.seeds import boards_for
from core.sources.spec import RawJob, RequestSpec, SearchCriteria, SourceDefinition

BASE = "https://apply.workable.com/api/v1/widget/accounts"


def query_mapper(criteria: SearchCriteria) -> list[RequestSpec]:
    boards = boards_for("workable", criteria.companies)
    return [RequestSpec(url=f"{BASE}/{b}?details=true", meta={"company": b})
            for b in boards]


def response_parser(raw, spec: RequestSpec) -> list[RawJob]:
    data = raw or {}
    company = (data.get("name") or spec.meta.get("company", "")).strip()
    out: list[RawJob] = []
    for j in data.get("jobs", []):
        title = (j.get("title") or "").strip()
        if not title:
            continue
        loc = ", ".join(p for p in (j.get("city"), j.get("state"), j.get("country")) if p)
        out.append(RawJob(
            title=title,
            company=company,
            location=loc or ("Remote" if j.get("telecommuting") else ""),
            description=strip_html(j.get("description") or "") or title,
            url=(j.get("url") or j.get("application_url") or "").strip(),
            source="workable",
            job_type=(j.get("employment_type") or "").strip(),
            posted=human_date(j.get("published_on")),
            remote=bool(j.get("telecommuting")),
            rich=True,
        ))
    return out


DEFINITION = SourceDefinition(
    slug="workable",
    display_name="Workable (ATS)",
    category="ats",
    adapter_type="api",
    base_url=BASE,
    auth_type="none",
    auth_env_key="",
    rate_limit_rpm=120,
    concurrency_limit=4,
    robots_check=True,
    query_mapper=query_mapper,
    response_parser=response_parser,
    note="Employer-direct postings from Workable job boards.",
)
