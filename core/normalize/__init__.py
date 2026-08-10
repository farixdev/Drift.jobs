"""Normalization (Phase 8): RawJob → canonical NormalizedJob.

Maps every raw result onto the canonical `job` schema — structured location,
parsed salary, UTC dates, controlled employment/seniority vocab, canonical
company + canonicalized URL — and computes the content fingerprint + simhash the
deduper needs. Only what the source states is normalized; absent data stays null.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.normalize.fields import (
    canonical_company,
    infer_seniority,
    normalize_employment,
    parse_location,
    parse_posted,
    parse_salary,
)

# Source authority tiers: employer-direct ATS beats aggregators beats feeds.
_AUTHORITY = {
    "greenhouse": 3, "lever": 3, "ashby": 3, "workable": 3, "smartrecruiters": 3,
    "themuse": 2, "arbeitnow": 2, "jobicy": 2, "remoteok": 2, "remotive": 2,
    "wwr": 1, "hn": 1, "custom": 1,
    "bing": 0, "google": 0,
}


@dataclass
class NormalizedJob:
    fingerprint: str
    simhash: int
    title: str
    company_name: str
    company_domain: str
    location_raw: str
    location_city: str
    location_region: str
    location_country: str
    work_mode: str
    employment_type: str
    seniority: str
    salary_min: int | None
    salary_max: int | None
    salary_currency: str
    salary_period: str
    salary_is_estimated: bool
    description_text: str
    apply_url: str
    canonical_url: str
    posted_at: str | None
    posted_at_is_approximate: bool
    source: str
    authority: int
    raw_url: str = ""
    alt_urls: list = field(default_factory=list)
    seen_count: int = 1
    sources: list = field(default_factory=list)


def normalize_job(raw) -> NormalizedJob:
    # Lazy imports break the core.normalize <-> core.dedup package cycle.
    from core.dedup.fingerprint import content_fingerprint
    from core.dedup.simhash import simhash
    from core.dedup.urls import canonicalize_url

    company = canonical_company(raw.company)
    loc = parse_location(raw.location, remote_flag=getattr(raw, "remote", None))
    sal = parse_salary(getattr(raw, "salary", "") or "")
    posted = parse_posted(getattr(raw, "posted", "") or "")
    canon_url = canonicalize_url(getattr(raw, "url", "") or "")
    emp = normalize_employment(getattr(raw, "job_type", "") or "")
    return NormalizedJob(
        fingerprint=content_fingerprint(company, raw.title, loc["city"]),
        simhash=simhash(raw.description or raw.title or ""),
        title=(raw.title or "").strip(),
        company_name=company,
        company_domain="",  # honest: no verified free domain-resolution API
        location_raw=(raw.location or "").strip(),
        location_city=loc["city"],
        location_region=loc["region"],
        location_country=loc["country"],
        work_mode=loc["work_mode"],
        employment_type=emp,
        seniority=infer_seniority(raw.title, emp),
        salary_min=sal["min"],
        salary_max=sal["max"],
        salary_currency=sal["currency"],
        salary_period=sal["period"],
        salary_is_estimated=sal["is_estimated"],
        description_text=(raw.description or "")[:8000],
        apply_url=(raw.url or "").strip(),
        canonical_url=canon_url,
        posted_at=posted["iso"],
        posted_at_is_approximate=posted["is_approximate"],
        source=raw.source,
        authority=_AUTHORITY.get(raw.source, 1),
        raw_url=(raw.url or "").strip(),
        sources=[raw.source],
    )


__all__ = ["NormalizedJob", "normalize_job"]
