"""Apply a SearchCriteria to normalized jobs (post-fetch filtering).

Most criteria can't be pushed to the ATS boards (they return a company's whole
board), so they're enforced here against `NormalizedJob`s: excluded/required
keywords, seniority, location mode + geography, salary floor, employment type,
company include/exclude + staffing, freshness, and the per-company cap. Returns
the surviving jobs and a per-reason drop tally for the UI.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.normalize.fields import company_key

_STAFFING = ("staffing", "recruit", "talent", "consultanc", "agency", "solutions",
             "technologies inc", "resourcing", "manpower")


def _text(nj) -> str:
    return f"{nj.title} {nj.description_text} {nj.company_name}".lower()


def _age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def _passes(nj, c) -> tuple[bool, str]:
    text = _text(nj)

    # excluded keywords
    for kw in c.keywords_excluded:
        if kw.lower() in text:
            return False, "excluded_keyword"
    # required keywords (all must appear somewhere)
    for kw in c.keywords_required:
        if kw.lower() not in text:
            return False, "missing_required"

    # seniority (if specified, the job's inferred seniority must be in the set)
    if c.seniority and nj.seniority and nj.seniority not in c.seniority:
        return False, "seniority"

    # location mode
    if c.location_mode and c.location_mode != "any":
        if nj.work_mode != "unspecified" and nj.work_mode != c.location_mode:
            # remote-friendly override: a remote-mode search accepts remote jobs
            return False, "location_mode"
    # geography (country match if countries specified and job has a country)
    if c.countries and nj.location_country:
        if not any(country.lower() in nj.location_country.lower()
                   or nj.location_country.lower() in country.lower()
                   for country in c.countries):
            # remote jobs bypass country restriction unless remote_in_country set
            if nj.work_mode != "remote":
                return False, "country"

    # salary floor (only when the job states a salary, unless include_unstated is off)
    stated = nj.salary_min or nj.salary_max
    if c.salary_min:
        if stated:
            top = nj.salary_max or nj.salary_min
            if top and top < c.salary_min:
                return False, "salary"
        elif not c.include_unstated_salary:
            return False, "salary_unstated"

    # employment type
    if c.employment_types and nj.employment_type:
        if nj.employment_type not in c.employment_types:
            return False, "employment_type"

    # company include/exclude
    ckey = company_key(nj.company_name)
    if c.only_companies and ckey not in {company_key(x) for x in c.only_companies}:
        return False, "not_in_only_companies"
    if c.exclude_companies and ckey in {company_key(x) for x in c.exclude_companies}:
        return False, "excluded_company"
    if c.exclude_staffing and any(s in nj.company_name.lower() for s in _STAFFING):
        return False, "staffing_agency"
    if c.exclude_domains:
        url = (nj.canonical_url or nj.apply_url or "").lower()
        if any(dom.lower() in url for dom in c.exclude_domains):
            return False, "excluded_domain"

    # freshness
    if c.posted_within_days:
        age = _age_days(nj.posted_at)
        if age is not None and age > c.posted_within_days:
            return False, "too_old"

    return True, ""


def apply_criteria(normalized: list, criteria) -> tuple[list, dict]:
    """Return (surviving_jobs, {reason: count}). Enforces per-company cap and the
    max_results hard cap after per-job filtering."""
    survivors: list = []
    dropped: dict[str, int] = {}
    per_company: dict[str, int] = {}
    cap = criteria.max_per_company or 0

    for nj in normalized:
        ok, reason = _passes(nj, criteria)
        if not ok:
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        if cap:
            ck = company_key(nj.company_name)
            if per_company.get(ck, 0) >= cap:
                dropped["max_per_company"] = dropped.get("max_per_company", 0) + 1
                continue
            per_company[ck] = per_company.get(ck, 0) + 1
        survivors.append(nj)

    if criteria.max_results and len(survivors) > criteria.max_results:
        dropped["max_results"] = len(survivors) - criteria.max_results
        survivors = survivors[: criteria.max_results]
    return survivors, dropped
