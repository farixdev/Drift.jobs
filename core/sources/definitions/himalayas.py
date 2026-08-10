"""Himalayas — public remote-jobs API, key-free (verified 2026-08-10).

API: https://himalayas.app/jobs/api?limit=N — single endpoint, all remote roles,
with full descriptions, salary, seniority, and an application link. robots.txt
allows our UA.
"""
from __future__ import annotations

from core.scraper.util import human_date, money, strip_html
from core.sources.spec import RawJob, RequestSpec, SearchCriteria, SourceDefinition

BASE = "https://himalayas.app/jobs/api"


def query_mapper(criteria: SearchCriteria) -> list[RequestSpec]:
    return [RequestSpec(url=f"{BASE}?limit=100")]


def response_parser(raw, spec: RequestSpec) -> list[RawJob]:
    out: list[RawJob] = []
    for j in (raw or {}).get("jobs", []):
        title = (j.get("title") or "").strip()
        if not title:
            continue
        locs = j.get("locationRestrictions") or []
        cur = j.get("currency") or "USD"
        sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(cur, "$")
        salary = money(j.get("minSalary"), j.get("maxSalary")).replace("$", sym) \
            if (j.get("minSalary") or j.get("maxSalary")) else ""
        out.append(RawJob(
            title=title,
            company=(j.get("companyName") or "").strip(),
            location=", ".join(locs) or "Remote",
            description=strip_html(j.get("description") or j.get("excerpt") or "") or title,
            url=(j.get("applicationLink") or j.get("guid") or "").strip(),
            source="himalayas",
            job_type=(j.get("employmentType") or "").strip(),
            salary=salary,
            posted=human_date(j.get("pubDate")),
            remote=True,
            rich=True,
        ))
    return out


DEFINITION = SourceDefinition(
    slug="himalayas",
    display_name="Himalayas",
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
    note="Public remote-jobs API, full descriptions + salary.",
)
