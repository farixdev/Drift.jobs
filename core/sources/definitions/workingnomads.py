"""Working Nomads — public remote-jobs API, key-free (verified 2026-08-10).

API: https://www.workingnomads.com/api/exposed_jobs/ — single endpoint returning
remote roles with a direct apply URL, HTML description, company, tags, and date.
robots.txt allows our UA.
"""
from __future__ import annotations

from core.scraper.util import human_date, strip_html
from core.sources.spec import RawJob, RequestSpec, SearchCriteria, SourceDefinition

BASE = "https://www.workingnomads.com/api/exposed_jobs/"


def query_mapper(criteria: SearchCriteria) -> list[RequestSpec]:
    return [RequestSpec(url=BASE)]


def response_parser(raw, spec: RequestSpec) -> list[RawJob]:
    out: list[RawJob] = []
    for j in raw or []:
        title = (j.get("title") or "").strip()
        url = (j.get("url") or "").strip()
        if not title or not url:
            continue
        out.append(RawJob(
            title=title,
            company=(j.get("company_name") or "").strip(),
            location=(j.get("location") or "Remote").strip() or "Remote",
            description=strip_html(j.get("description") or "") or title,
            url=url,
            source="workingnomads",
            job_type=(j.get("category_name") or "").strip(),
            posted=human_date(j.get("pub_date")),
            remote=True,
            rich=True,
        ))
    return out


DEFINITION = SourceDefinition(
    slug="workingnomads",
    display_name="Working Nomads",
    category="aggregator",
    adapter_type="api",
    base_url=BASE,
    auth_type="none",
    auth_env_key="",
    rate_limit_rpm=60,
    concurrency_limit=1,
    robots_check=True,
    query_mapper=query_mapper,
    response_parser=response_parser,
    note="Public remote-jobs API with direct apply URLs.",
)
