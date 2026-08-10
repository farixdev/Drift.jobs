"""Ashby job boards — public, key-free, employer-canonical.

API: https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true
Returns jobs with `descriptionHtml`, an explicit `isRemote` flag, and (when the
employer opts in) a compensation object. Ashby serves no robots.txt (401);
absence of rules is treated as allowed (verified 2026-08-10).
"""
from __future__ import annotations

from core.scraper.util import human_date, strip_html
from core.sources.seeds import boards_for
from core.sources.spec import RawJob, RequestSpec, SearchCriteria, SourceDefinition

BASE = "https://api.ashbyhq.com/posting-api/job-board"


def query_mapper(criteria: SearchCriteria) -> list[RequestSpec]:
    boards = boards_for("ashby", criteria.companies)
    return [RequestSpec(url=f"{BASE}/{b}?includeCompensation=true", meta={"company": b})
            for b in boards]


def _salary(job) -> str:
    comp = job.get("compensation") or {}
    summary = comp.get("compensationTierSummary")
    return summary.strip() if isinstance(summary, str) else ""


def response_parser(raw, spec: RequestSpec) -> list[RawJob]:
    board = spec.meta.get("company", "")
    out: list[RawJob] = []
    for j in (raw or {}).get("jobs", []):
        if j.get("isListed") is False:
            continue
        title = (j.get("title") or "").strip()
        if not title:
            continue
        out.append(RawJob(
            title=title,
            company=board.title(),
            location=(j.get("location") or "").strip(),
            description=strip_html(j.get("descriptionHtml") or "") or title,
            url=(j.get("jobUrl") or j.get("applyUrl") or "").strip(),
            source="ashby",
            job_type=(j.get("employmentType") or "").strip(),
            salary=_salary(j),
            posted=human_date(j.get("publishedAt")),
            remote=bool(j.get("isRemote")),
            rich=True,
        ))
    return out


DEFINITION = SourceDefinition(
    slug="ashby",
    display_name="Ashby (ATS)",
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
    note="Employer-direct postings from Ashby job boards.",
)
