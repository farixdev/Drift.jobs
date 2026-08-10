"""Recruitee job boards — public, key-free, employer-canonical.

API: https://{token}.recruitee.com/api/offers/ — one request per company returns
its offers with HTML descriptions, location, and a public careers URL. robots.txt
(via the company's careers host) allows the /api/offers/ path (verified 2026-08-11).
"""
from __future__ import annotations

from core.scraper.util import human_date, strip_html
from core.sources.seeds import boards_for
from core.sources.spec import RawJob, RequestSpec, SearchCriteria, SourceDefinition


def query_mapper(criteria: SearchCriteria) -> list[RequestSpec]:
    boards = boards_for("recruitee", criteria.companies)
    return [RequestSpec(url=f"https://{b}.recruitee.com/api/offers/", meta={"company": b})
            for b in boards]


def _location(job) -> str:
    loc = job.get("location")
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    city = (job.get("city") or "").strip()
    country = (job.get("country") or job.get("country_code") or "").strip()
    return ", ".join(p for p in (city, country) if p)


def _salary(job) -> str:
    s = job.get("salary")
    if isinstance(s, str):
        return s.strip()
    if isinstance(s, dict):
        lo, hi = s.get("min"), s.get("max")
        cur = s.get("currency") or ""
        if lo or hi:
            return f"{cur} {lo or ''}–{hi or ''}".strip()
    return ""


def response_parser(raw, spec: RequestSpec) -> list[RawJob]:
    board = spec.meta.get("company", "")
    out: list[RawJob] = []
    for j in (raw or {}).get("offers", []):
        title = (j.get("title") or "").strip()
        if not title:
            continue
        loc = _location(j)
        out.append(RawJob(
            title=title,
            company=(j.get("company_name") or board.title()).strip(),
            location=loc,
            description=strip_html(j.get("description") or "") or title,
            url=(j.get("careers_url") or j.get("careers_apply_url") or "").strip(),
            source="recruitee",
            job_type=(j.get("employment_type") or "").strip(),
            salary=_salary(j),
            posted=human_date(j.get("published_at")),
            remote=bool(j.get("remote")) or "remote" in loc.lower(),
            rich=True,
        ))
    return out


DEFINITION = SourceDefinition(
    slug="recruitee",
    display_name="Recruitee (ATS)",
    category="ats",
    adapter_type="api",
    base_url="https://recruitee.com",
    auth_type="none",
    auth_env_key="",
    rate_limit_rpm=60,
    concurrency_limit=2,
    robots_check=True,
    query_mapper=query_mapper,
    response_parser=response_parser,
    note="Employer-direct postings from Recruitee company boards.",
)
