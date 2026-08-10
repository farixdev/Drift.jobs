"""Transparent scoring rubric (Phase 4) — resume vs a specific job.

Scores across eight named dimensions, each with a 0..100 score and a plain-English
detail, then a weighted composite. Dimensions with no evidence in the job are
marked neutral and excluded from the weighting rather than guessed. Returns the
composite, the per-dimension breakdown, and `missing[]` / `strengths[]` — so the
number is always decomposable and explainable (Phase 8 rule).
"""
from __future__ import annotations

import re

from core.normalize.fields import infer_seniority
from core.resume.keywords import seniority_band, weighted_skills, years_experience

_DIM_WEIGHTS = {
    "hard_skills": 0.30,
    "experience_years": 0.15,
    "seniority": 0.12,
    "domain": 0.10,
    "education": 0.08,
    "location": 0.10,
    "salary": 0.05,
    "ats": 0.10,
}

_SENIORITY_RANK = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "principal": 4}
_DEGREE_RE = re.compile(r"(?i)\b(bachelor|master|phd|doctorate|bsc|msc|b\.?s\.?|m\.?s\.?|degree)\b")
_YEARS_RE = re.compile(r"(?i)(\d{1,2})\s*\+?\s*years?")


def _job_skills(job_text: str) -> list[str]:
    from core import local_engine
    from core.skills_db import TECH_SKILLS
    found = []
    for s in TECH_SKILLS:
        if local_engine._contains_skill(job_text, s):
            found.append(s)
    return found


def score_against_job(parsed, job: dict, *, criteria=None, ats_result: dict | None = None) -> dict:
    """`job` keys: title, description, seniority, location_country/city, work_mode,
    salary_min, salary_max. Returns the full rubric result."""
    jtext = f"{job.get('title','')} {job.get('description','')}"
    jlow = jtext.lower()
    dims: dict[str, dict] = {}
    missing: list[str] = []
    strengths: list[str] = []

    # 1) Hard-skill coverage — fraction of the posting's required skills the
    #    candidate has (count-based; the résumé-category weight must NOT shrink
    #    coverage, or a candidate who has every required skill as a "tool" would
    #    top out at 70%).
    resume_keys = {s.lower() for s, _w in weighted_skills(parsed)}
    job_sk = _job_skills(jtext)
    if job_sk:
        matched = [s for s in job_sk if s.lower() in resume_keys]
        gaps = [s for s in job_sk if s.lower() not in resume_keys]
        cov = len(matched) / len(job_sk)
        missing += gaps[:8]
        strengths += matched[:6]
        dims["hard_skills"] = {"score": round(cov * 100),
                               "detail": f"{len(matched)}/{len(job_sk)} required skills matched"}
    else:
        dims["hard_skills"] = {"score": None, "detail": "no explicit skills found in the posting"}

    # 2) Years of experience vs stated requirement. Only treat a "N years" mention
    #    as a REQUIREMENT when it carries a '+' or sits next to "experience" — so a
    #    stray "founded 2 years ago" isn't read as a 2-year requirement.
    req_years = None
    for m in re.finditer(r"(?i)(\d{1,2})\s*(\+)?\s*years?([^.]{0,25})", jlow):
        n, plus, tail = int(m.group(1)), m.group(2), m.group(3)
        if plus or "experien" in tail or "exp " in tail:
            req_years = n
            break
    have_years = years_experience(parsed)
    if req_years:
        ratio = min(1.0, have_years / req_years) if req_years else 1.0
        dims["experience_years"] = {"score": round(ratio * 100),
                                    "detail": f"{have_years:g} yrs vs {req_years}+ required"}
        if have_years < req_years:
            missing.append(f"{req_years}+ years experience")
    else:
        dims["experience_years"] = {"score": None, "detail": "no explicit year requirement"}

    # 3) Seniority alignment
    job_sen = job.get("seniority") or infer_seniority(job.get("title", ""))
    res_sen = seniority_band(parsed)
    if job_sen in _SENIORITY_RANK and res_sen in _SENIORITY_RANK:
        gap = abs(_SENIORITY_RANK[job_sen] - _SENIORITY_RANK[res_sen])
        dims["seniority"] = {"score": max(0, 100 - gap * 30),
                             "detail": f"you: {res_sen} · role: {job_sen}"}
    else:
        dims["seniority"] = {"score": None, "detail": "seniority not determinable"}

    # 4) Domain / industry overlap (shared significant terms)
    res_domain = _domain_terms(parsed)
    job_domain = set(re.findall(r"[a-z]{4,}", jlow))
    if res_domain:
        overlap = res_domain & job_domain
        dims["domain"] = {"score": round(min(1.0, len(overlap) / max(4, len(res_domain) / 3)) * 100),
                          "detail": f"{len(overlap)} shared domain terms"}
    else:
        dims["domain"] = {"score": None, "detail": "no domain terms parsed"}

    # 5) Education / certification — a real degree keyword scores full; unrelated
    #    education (e.g. a bootcamp / diploma) gets partial, not full, credit.
    if _DEGREE_RE.search(jlow):
        degree_text = " ".join(e.degree or "" for e in parsed.education)
        if _DEGREE_RE.search(degree_text):
            dims["education"] = {"score": 100, "detail": "matching degree present"}
        elif parsed.education:
            dims["education"] = {"score": 70, "detail": "education listed, no matching degree"}
        else:
            dims["education"] = {"score": 40, "detail": "posting expects a degree"}
            missing.append("a degree the posting expects")
    else:
        dims["education"] = {"score": None, "detail": "no education requirement stated"}

    # 6) Location / work-mode compatibility
    dims["location"] = _location_dim(parsed, job, criteria)

    # 7) Salary band overlap
    dims["salary"] = _salary_dim(job, criteria)

    # 8) ATS mechanical
    if ats_result:
        dims["ats"] = {"score": ats_result["score"], "detail": f"{ats_result['score']}/100 ATS checks"}
    else:
        dims["ats"] = {"score": None, "detail": "not evaluated"}

    # Composite over available dimensions (renormalize weights).
    parts = [(k, d["score"], _DIM_WEIGHTS.get(k, 0)) for k, d in dims.items()
             if d["score"] is not None]
    tot_w = sum(w for _, _, w in parts) or 1.0
    composite = round(sum(s * w for _, s, w in parts) / tot_w) if parts else 0

    return {
        "composite": max(0, min(100, composite)),
        "dimensions": dims,
        "missing": list(dict.fromkeys(missing))[:10],
        "strengths": list(dict.fromkeys(strengths))[:8],
    }


def _domain_terms(parsed) -> set[str]:
    text = " ".join([parsed.summary] + [e.title for e in parsed.experience]
                    + [b for e in parsed.experience for b in e.bullets]).lower()
    stop = {"with", "team", "using", "work", "years", "developed", "built", "responsible"}
    return {w for w in re.findall(r"[a-z]{5,}", text) if w not in stop}


def _location_dim(parsed, job, criteria) -> dict:
    mode = job.get("work_mode", "unspecified")
    if mode == "remote":
        return {"score": 100, "detail": "remote role — location-agnostic"}
    res_loc = ((parsed.contact or {}).get("location") or "").lower()
    country = (job.get("location_country") or "").lower()
    if not res_loc or not country:
        return {"score": None, "detail": "location not comparable"}
    if country and country in res_loc:
        return {"score": 100, "detail": "same country"}
    if criteria and getattr(criteria, "relocation_ok", False):
        return {"score": 70, "detail": "different country, open to relocation"}
    return {"score": 40, "detail": "different country"}


def _salary_dim(job, criteria) -> dict:
    want = getattr(criteria, "salary_min", None) if criteria else None
    top = job.get("salary_max") or job.get("salary_min")
    if not want or not top:
        return {"score": None, "detail": "no salary comparison possible"}
    if top >= want:
        return {"score": 100, "detail": f"meets your {want:,} floor"}
    return {"score": round(max(0, top / want) * 100), "detail": f"below your {want:,} floor"}
