"""Lever postings — public, key-free, employer-canonical.

API: https://api.lever.co/v0/postings/{token}?mode=json
Returns an array of postings with plain-text descriptions. robots.txt allows our
UA (verified 2026-08-10).
"""
from __future__ import annotations

from core.scraper.util import human_date
from core.sources.seeds import boards_for
from core.sources.spec import RawJob, RequestSpec, SearchCriteria, SourceDefinition

BASE = "https://api.lever.co/v0/postings"


def query_mapper(criteria: SearchCriteria) -> list[RequestSpec]:
    boards = boards_for("lever", criteria.companies)
    return [RequestSpec(url=f"{BASE}/{b}?mode=json", meta={"company": b})
            for b in boards]


def response_parser(raw, spec: RequestSpec) -> list[RawJob]:
    board = spec.meta.get("company", "")
    out: list[RawJob] = []
    for j in raw or []:
        title = (j.get("text") or "").strip()
        if not title:
            continue
        cats = j.get("categories") or {}
        loc = (cats.get("location") or "").strip()
        workplace = (j.get("workplaceType") or "").lower()
        desc = (j.get("descriptionPlain") or j.get("description") or title)[:6000]
        out.append(RawJob(
            title=title,
            company=board.title(),
            location=loc or ("Remote" if workplace == "remote" else ""),
            description=desc,
            url=(j.get("hostedUrl") or j.get("applyUrl") or "").strip(),
            source="lever",
            job_type=(cats.get("commitment") or "").strip(),
            posted=human_date(j.get("createdAt")),
            remote=workplace == "remote" or "remote" in loc.lower(),
            rich=True,
        ))
    return out


DEFINITION = SourceDefinition(
    slug="lever",
    display_name="Lever (ATS)",
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
    note="Employer-direct postings from Lever company boards.",
)
