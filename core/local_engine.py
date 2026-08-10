"""
Local resume parsing and job scoring — 100% on your machine.
No API keys, no quotas, no cloud. Also the free baseline that the LLM
reranker refines, and the fallback whenever no API key is configured.
"""

import re
from functools import lru_cache
from typing import Any

from core.skills_db import TECH_SKILLS as SKILLS

# Tokens that are also common English words: only count them in their canonical
# (capitalised/acronym) form so the language "Go" never matches the verb "go".
_PROSE = {"go": "Go", "r": "R", "c": "C", "d": "D", "a": "A", "rest": "REST"}

# Generic role words that make a title relevant even without an exact skill hit.
_ROLE_WORDS = (
    "engineer", "developer", "backend", "frontend", "fullstack", "full-stack",
    "full stack", "data", "devops", "designer", "scientist", "architect",
    "analyst", "programmer", "sysadmin", "sre", "mobile", "cloud", "security",
    "software", "machine learning",
)
_ROLE_WORDS_RE = re.compile(
    r"(?i)(?<![a-z])(" + "|".join(re.escape(w) for w in _ROLE_WORDS) + r")(?![a-z])"
)

_LOCATION_RE = re.compile(
    r"(?i)\b(?:based in|located in|location[:\s]+)\s*"
    r"([A-Za-z][A-Za-z\s,.'-]{2,40})"
)
_REMOTE_RE = re.compile(r"(?i)\b(remote|work from home|wfh|hybrid)\b")

# Words that look like "City, Region" captures but are really resume prose/headers.
_LOC_BLOCK = {
    "experience", "skills", "summary", "education", "projects", "objective",
    "profile", "references", "work", "employment", "professional", "technical",
    "contact", "languages", "certifications", "achievements", "interests",
    "university", "college", "bachelor", "master", "responsibilities", "present",
    "senior", "junior", "engineer", "manager", "developer", "lead", "director",
    "analyst", "designer", "specialist", "consultant", "intern", "architect",
}

# Multi-letter acronyms whose canonical display form is all-caps.
_ACRONYMS = {
    "html", "http", "https", "json", "xml", "yaml", "toml", "ajax", "saas",
    "paas", "iaas", "wcag", "grpc", "graphql", "restful", "oauth", "jwt",
}

_CITIES = (
    "Lahore", "Karachi", "Islamabad", "Rawalpindi", "London", "New York",
    "San Francisco", "Toronto", "Berlin", "Dubai", "Singapore", "Sydney",
    "Mumbai", "Delhi", "Bangalore", "Amsterdam", "Dublin", "Austin",
)
_CITIES_LOWER = frozenset(c.lower() for c in _CITIES)

# Countries whose name confirms a "City, Country" candidate is a real place.
_COUNTRIES = frozenset({
    "canada", "pakistan", "india", "united states", "usa", "us", "america",
    "united kingdom", "uk", "england", "scotland", "wales", "ireland",
    "germany", "france", "spain", "italy", "netherlands", "belgium",
    "switzerland", "austria", "sweden", "norway", "denmark", "finland",
    "poland", "portugal", "greece", "turkey", "romania", "czechia",
    "australia", "new zealand", "singapore", "malaysia", "indonesia",
    "philippines", "thailand", "vietnam", "japan", "china", "korea",
    "taiwan", "brazil", "argentina", "chile", "colombia", "mexico",
    "egypt", "nigeria", "kenya", "south africa", "israel", "saudi arabia",
    "uae", "united arab emirates", "qatar", "kuwait", "bahrain",
    "bangladesh", "sri lanka", "nepal", "ukraine", "hungary",
})
# US state + Canadian province codes that confirm a "City, XX" candidate.
_REGION_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE",
})
# Zero-width lookahead so overlapping candidates ("Engineer, Toronto" vs
# "Toronto, Canada") are BOTH surfaced instead of the first one consuming text.
_PLACE_RE = re.compile(
    r"(?=\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,2}),\s*"
    r"([A-Z][A-Za-z.]+|[A-Z]{2})\b)"
)


@lru_cache(maxsize=8192)
def _pattern(token: str, cased: bool) -> re.Pattern:
    """Token-aware boundary matcher: '+', '#', '.' count as part of a token, so
    'c' won't match inside 'c++'. `cased` = case-sensitive (for canonical prose)."""
    esc = re.escape(token)
    flags = 0 if cased else re.I
    return re.compile(rf"(?<![a-zA-Z0-9+#.]){esc}(?![a-zA-Z0-9+#.])", flags)


def _contains_skill(text: str, skill: str) -> bool:
    key = skill.lower()
    if key in _PROSE:  # match only the canonical capitalisation, case-sensitively
        return bool(_pattern(_PROSE[key], True).search(text))
    return bool(_pattern(key, False).search(text))


def _first_pos(text: str, skill: str) -> int:
    key = skill.lower()
    pat = _pattern(_PROSE[key], True) if key in _PROSE else _pattern(key, False)
    m = pat.search(text)
    return m.start() if m else 10**9


def _normalize_skill(skill: str) -> str:
    s = skill.strip()
    if s.lower() in _PROSE:
        return _PROSE[s.lower()]
    if s.lower() in ("c#", "c++", ".net"):
        return s
    if s.lower() in _ACRONYMS or (len(s) <= 3 and s.isalpha()):
        return s.upper()
    return s.title() if s.islower() else s


def extract_skills(resume_text: str) -> list[str]:
    matched: list[str] = []
    seen: set[str] = set()
    for skill in SKILLS:
        key = skill.lower()
        if key in seen or not _contains_skill(resume_text, skill):
            continue
        seen.add(key)
        matched.append(skill)
    # Order by where they appear in the resume (top skills first), not alphabetically.
    matched.sort(key=lambda s: (_first_pos(resume_text, s), -len(s)))
    return [_normalize_skill(s) for s in matched][:30]


def extract_location(resume_text: str) -> str:
    # 1) Explicit "based in / located in / location:" wins.
    m = _LOCATION_RE.search(resume_text)
    if m:
        loc = m.group(1).strip().rstrip(".,;")
        if len(loc) > 2 and not _looks_like_prose(loc):
            return loc
    # 2) A "City, Region" pair — but only if the region is a real place, so
    #    skill lists like "Python, Django" can never be mistaken for a location.
    for m in _PLACE_RE.finditer(resume_text):
        city = m.group(1).strip().rstrip(".,;")
        region = m.group(2).strip().rstrip(".,;")
        words = re.findall(r"[A-Za-z]+", f"{city} {region}".lower())
        if any(w in _LOC_BLOCK for w in words):
            continue
        if (region in _REGION_CODES or region.lower() in _COUNTRIES
                or city.lower() in _CITIES_LOWER):
            return f"{city}, {region}"
    # 3) A bare known city.
    for city in _CITIES:
        if re.search(rf"\b{re.escape(city)}\b", resume_text, re.I):
            return city
    return "Remote"


def _looks_like_prose(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text.lower())
    return any(w in _LOC_BLOCK for w in words) or len(words) > 4


def generate_keywords(skills: list[str]) -> list[str]:
    if not skills:
        return ["software developer", "engineer"]
    primary = skills[0]
    # One role phrase + concrete skill tokens (avoids every keyword sharing
    # the generic word "developer", which pollutes relevance filtering).
    keywords = [f"{primary} developer"]
    for s in skills[1:4]:
        if s.lower() != primary.lower():
            keywords.append(s)
    if len(keywords) == 1:
        keywords.append(primary)
    return keywords[:5]


def parse_resume(resume_text: str) -> dict[str, Any]:
    skills = extract_skills(resume_text)
    return {
        "skills": skills,
        "location": extract_location(resume_text),
        "keywords": generate_keywords(skills),
    }


_ROLE_STOP = {
    "senior", "junior", "mid", "staff", "principal", "lead", "remote", "hybrid",
    "the", "and", "for", "with", "years", "year", "experience", "your", "profile",
    "new", "full", "time", "contract", "developer",  # too generic on its own
}


def role_terms(keywords: list[str], skills: list[str] | None = None) -> set[str]:
    """Significant role/skill tokens used to judge title relevance & filter noise."""
    terms: set[str] = set()
    for kw in keywords or []:
        for w in re.split(r"[^A-Za-z0-9+#.]+", kw):
            wl = w.lower()
            if len(wl) > 2 and wl not in _ROLE_STOP:
                terms.add(wl)
    for s in (skills or [])[:6]:
        if s:
            terms.add(s.lower())
    return terms


def _title_hits(title: str, matched: list[str], terms: set[str]) -> int:
    hits = sum(1 for s in matched if _contains_skill(title, s))
    hits += sum(1 for t in terms if t not in {m.lower() for m in matched}
                and _contains_skill(title, t))
    return hits


def is_relevant(
    candidate_skills: list[str],
    terms: set[str],
    title: str,
    description: str,
) -> bool:
    """True if a job plausibly matches the candidate — used to drop feed noise
    (e.g. a writer/sales role for a backend engineer) before scoring."""
    text = f"{title} {description}"
    skill_hits = sum(1 for s in candidate_skills if s and _contains_skill(text, s))
    title_role_hits = sum(1 for t in terms if _contains_skill(title, t))
    return skill_hits >= 2 or title_role_hits >= 2 or (skill_hits >= 1 and title_role_hits >= 1)


def analyze(
    candidate_skills: list[str],
    title: str,
    description: str,
    terms: set[str] | None = None,
) -> dict[str, Any]:
    """The heart of local scoring: compare a candidate's skills to a job.

    Returns matched skills, missing skills (skills the job asks for that the
    candidate lacks), a 0–100 fit score, a verdict, and a summary.
    """
    title = title or ""
    description = description or ""
    text = f"{title}\n{description}"
    cand = [s for s in (candidate_skills or []) if s]
    terms = terms or set()

    matched = [s for s in cand if _contains_skill(text, s)]

    # Skills the job appears to require, mined from the JD (tech skills only).
    job_skills: list[str] = []
    job_seen: set[str] = set()
    for skill in SKILLS:
        low = skill.lower()
        if low in job_seen or (len(low) == 1):  # skip single-letter noise in gaps
            continue
        if _contains_skill(text, skill):
            job_seen.add(low)
            job_skills.append(_normalize_skill(skill))

    cand_lower = {s.lower() for s in cand}
    missing = [s for s in job_skills if s.lower() not in cand_lower][:8]

    n_match = len(matched)

    # Absolute overlap is the primary signal; coverage is secondary (denominator
    # capped so skill-heavy JDs aren't unfairly penalised); title relevance gives
    # full credit for an aligned role even on a generic title.
    match_strength = min(1.0, n_match / 5)
    coverage = n_match / max(min(len(job_skills), 6), 1)
    title_hits = _title_hits(title, matched, terms)
    if title_hits >= 2:
        role_relevance = 1.0
    elif title_hits == 1:
        role_relevance = 0.75
    elif _ROLE_WORDS_RE.search(title):
        role_relevance = 0.5
    else:
        role_relevance = 0.0

    score = int(round(100 * (
        0.40 * match_strength
        + 0.25 * coverage
        + 0.35 * role_relevance
    )))
    score = max(0, min(100, score))

    if matched:
        top = ", ".join(matched[:3])
        summary = f"Title & skills align — {top}." if title_hits else f"Overlap on {top}."
    else:
        summary = "No clear skill overlap with your resume."

    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "verdict": _verdict(score),
        "summary": summary,
    }


def _verdict(score: int) -> str:
    if score >= 80:
        return "Strong match"
    if score >= 60:
        return "Good match"
    if score >= 40:
        return "Partial match"
    if score > 0:
        return "Weak match"
    return "No match"


# --- Back-compat shims (older callers) ------------------------------------

def score_job(
    resume_text: str,
    job_description: str,
    skills: list[str] | None = None,
    title: str = "",
) -> dict[str, Any]:
    skills = skills or extract_skills(resume_text)
    return analyze(skills, title, job_description)


def score_jobs_batch(
    resume_text: str,
    jobs: list[dict],
    skills: list[str] | None = None,
) -> list[dict]:
    skills = skills or extract_skills(resume_text)
    return [
        {"id": i, **analyze(skills, job.get("title") or "", job.get("description") or "")}
        for i, job in enumerate(jobs)
    ]
