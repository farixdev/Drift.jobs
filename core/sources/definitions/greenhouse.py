"""Greenhouse job boards — public, key-free, employer-canonical postings.

API: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
One request per company board returns all its jobs with full (HTML-entity-encoded)
descriptions. robots.txt allows our UA (verified 2026-08-10).
"""
from __future__ import annotations

import html

from core.scraper.util import human_date, strip_html
from core.sources.seeds import boards_for
from core.sources.spec import RawJob, RequestSpec, SearchCriteria, SourceDefinition

BASE = "https://boards-api.greenhouse.io/v1/boards"


def query_mapper(criteria: SearchCriteria) -> list[RequestSpec]:
    boards = boards_for("greenhouse", criteria.companies)
    return [RequestSpec(url=f"{BASE}/{b}/jobs?content=true", meta={"company": b})
            for b in boards]


def response_parser(raw, spec: RequestSpec) -> list[RawJob]:
    board = spec.meta.get("company", "")
    out: list[RawJob] = []
    for j in (raw or {}).get("jobs", []):
        title = (j.get("title") or "").strip()
        if not title:
            continue
        loc = ((j.get("location") or {}).get("name") or "").strip()
        # `content` is HTML with entities double-encoded — unescape then strip.
        content = strip_html(html.unescape(j.get("content") or "")) or title
        out.append(RawJob(
            title=title,
            company=(j.get("company_name") or board.title()).strip(),
            location=loc or ("Remote" if "remote" in content.lower()[:200] else ""),
            description=content,
            url=(j.get("absolute_url") or "").strip(),
            source="greenhouse",
            posted=human_date(j.get("updated_at") or j.get("first_published")),
            remote="remote" in loc.lower(),
            rich=True,
        ))
    return out


DEFINITION = SourceDefinition(
    slug="greenhouse",
    display_name="Greenhouse (ATS)",
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
    note="Employer-direct postings from Greenhouse company boards.",
)
