"""
Local resume parsing and job scoring — 100% on your machine.
No API keys, no quotas, no cloud. Also the free baseline that the LLM
reranker refines, and the fallback whenever no API key is configured.
"""

import re
from functools import lru_cache
from typing import Any

from core.skills_db import SKILLS

# Single/short tokens that produce false positives when scanned against raw job
# text (e.g. the letter "r" or the word "go"). We still honour them when they
# come from a resume's own curated skill list — just not when mining a JD.
_AMBIGUOUS = {"r", "c", "d", "go", "a"}

_LOCATION_RE = re.compile(
    r"(?i)\b(?:based in|located in|location[:\s]+)\s*"
    r"([A-Za-z][A-Za-z\s,.'-]{2,60})"
)
_CITY_COUNTRY_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s*[A-Z][a-z][A-Za-z\s]+)\b"
)
_REMOTE_RE = re.compile(r"(?i)\b(remote|work from home|wfh|hybrid)\b")

_CITIES = (
    "Lahore", "Karachi", "Islamabad", "Rawalpindi", "London", "New York",
    "San Francisco", "Toronto", "Berlin", "Dubai", "Singapore", "Sydney",
    "Mumbai", "Delhi", "Bangalore", "Amsterdam", "Dublin", "Austin", "Remote",
)


@lru_cache(maxsize=8192)
def _skill_pattern(skill: str, strict: bool) -> re.Pattern:
    """Token-aware matcher: '+', '#', '.' count as part of a token, so 'c'
    won't match inside 'c++' and vice-versa. `strict` = case-sensitive, used for
    short/ambiguous skills so the language 'Go' doesn't match the verb 'go'."""
    esc = re.escape(skill)
    flags = 0 if strict else re.I
    return re.compile(rf"(?<![a-zA-Z0-9+#.]){esc}(?![a-zA-Z0-9+#.])", flags)


def _contains_skill(text: str, skill: str) -> bool:
    strict = len(skill) <= 2 or skill.lower() in _AMBIGUOUS
    return bool(_skill_pattern(skill, strict).search(text))


def _normalize_skill(skill: str) -> str:
    s = skill.strip()
    if s.lower() in ("c#", "c++", ".net"):
        return s
    return s.title() if s.islower() else s


def extract_skills(resume_text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for skill in sorted(SKILLS, key=len, reverse=True):
        if _contains_skill(resume_text, skill):
            key = skill.lower()
            if key not in seen:
                seen.add(key)
                found.append(_normalize_skill(skill))
    return found[:30]


def extract_location(resume_text: str) -> str:
    for pattern in (_LOCATION_RE, _CITY_COUNTRY_RE):
        match = pattern.search(resume_text)
        if match:
            loc = match.group(1).strip().rstrip(".,;")
            if len(loc) > 2:
                return loc
    for city in _CITIES:
        if re.search(rf"\b{re.escape(city)}\b", resume_text, re.I):
            return city
    return "Remote"


def generate_keywords(skills: list[str]) -> list[str]:
    if not skills:
        return ["software developer", "engineer"]
    keywords = [f"{skill} developer" for skill in skills[:3]]
    if len(keywords) < 3:
        keywords.append(" ".join(skills[:2]))
    return keywords[:5]


def parse_resume(resume_text: str) -> dict[str, Any]:
    skills = extract_skills(resume_text)
    return {
        "skills": skills,
        "location": extract_location(resume_text),
        "keywords": generate_keywords(skills),
    }


def analyze(candidate_skills: list[str], title: str, description: str) -> dict[str, Any]:
    """The heart of local scoring: compare a candidate's skills to a job.

    Returns matched skills, missing skills (skills the job asks for that the
    candidate lacks), a 0–100 fit score, a verdict, and a summary.
    """
    title = title or ""
    description = description or ""
    text = f"{title}\n{description}"
    cand = [s for s in (candidate_skills or []) if s]

    matched = [s for s in cand if _contains_skill(text, s)]

    # Skills the job appears to require, mined from the JD.
    job_skills: list[str] = []
    job_seen: set[str] = set()
    for skill in SKILLS:
        if skill in _AMBIGUOUS:
            continue
        if _contains_skill(text, skill) and skill.lower() not in job_seen:
            job_seen.add(skill.lower())
            job_skills.append(_normalize_skill(skill))

    cand_lower = {s.lower() for s in cand}
    missing = [s for s in job_skills if s.lower() not in cand_lower][:8]

    n_match = len(matched)
    n_job = max(len(job_skills), 1)
    coverage = n_match / n_job
    title_hits = sum(1 for s in matched if _contains_skill(title, s))

    score = int(round(100 * (
        0.55 * coverage
        + 0.30 * min(1.0, n_match / 5)
        + 0.15 * min(1.0, title_hits / 2)
    )))
    score = max(0, min(100, score))

    verdict = _verdict(score)
    if matched:
        top = ", ".join(matched[:3])
        summary = f"Title & skills align — {top}." if title_hits else f"Overlap on {top}."
    else:
        summary = "No clear skill overlap with your resume."

    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "verdict": verdict,
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
