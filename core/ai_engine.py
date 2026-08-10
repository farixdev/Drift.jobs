"""Thin task-shaped facade over the Phase 3 provider layer.

Keeps the exact call surface the 1.x app depends on (`has_api_key`,
`reset_client`, `parse_resume`, `score_jobs_batch`, `generate_cover_letter`)
but routes every call through `core.ai.LLMManager`: multi-provider, bring-your-
own-key, with fallback chains, structured-output repair, caching, and cost
metering. The old Groq-only OpenAI client is gone; Groq is now just one provider
behind the router (and still the default route, so behaviour is preserved).

Model routing per task lives in `core.ai.routing`; keys live in the OS keychain
via `core.ai.keystore`. This module holds no keys and makes no direct HTTP calls.
"""
from __future__ import annotations

import json
from typing import Any

from core.ai import routing
from core.ai.keystore import default_store
from core.ai.manager import LLMManager
from core.ai.registry import PROVIDERS
from core.ai.types import Message

_manager: LLMManager | None = None


def _mgr() -> LLMManager:
    global _manager
    if _manager is None:
        _manager = LLMManager()
    return _manager


def reset_client() -> None:
    """Drop cached manager/providers so a newly saved key or route takes effect."""
    global _manager
    _manager = None
    from core.ai.factory import reset_providers
    from core.ai.keystore import reset_default_store
    reset_default_store()
    reset_providers()


def _task_available(task: str) -> bool:
    """True when the task's route has at least one usable provider (keyless, or a
    key on file)."""
    store = default_store()
    for provider_slug, _model in routing.get_route(task).chain():
        spec = PROVIDERS.get(provider_slug)
        if spec is None:
            continue
        if not spec.needs_key or store.has_key(provider_slug):
            return True
    return False


def has_api_key() -> bool:
    """Whether LLM scoring/cover-letters are available (the reranker route is
    served). Name kept for 1.x callers; now provider-agnostic."""
    return _task_available("job_rerank") or _task_available("cover_letter")


# --------------------------------------------------------------------------- #
# Resume parsing
# --------------------------------------------------------------------------- #
_RESUME_SCHEMA = {
    "type": "object",
    "required": ["skills", "location", "keywords"],
    "properties": {
        "skills": {"type": "array", "items": {"type": "string"}},
        "location": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
}


def parse_resume(resume_text: str) -> dict[str, Any]:
    prompt = f"""From this resume return ONLY JSON of this exact shape:
{{"skills": ["skill1"], "location": "City, Country or Remote", "keywords": ["search phrase 1"]}}
Max 20 skills, 3-5 keywords.

Resume:
{resume_text[:3500]}"""
    obj, _ = _mgr().run_structured(
        "resume_parse",
        [Message("system", "You return only valid JSON. No markdown."),
         Message("user", prompt)],
        _RESUME_SCHEMA,
    )
    data = obj if isinstance(obj, dict) else {}

    def _clean(value) -> list[str]:
        out: list[str] = []
        for item in value if isinstance(value, list) else []:
            if isinstance(item, (str, int, float)):
                s = str(item).strip()
            elif isinstance(item, dict):
                s = str(item.get("name") or item.get("skill") or "").strip()
            else:
                s = ""
            if s:
                out.append(s)
        return out

    skills = _clean(data.get("skills"))
    keywords = _clean(data.get("keywords")) or skills[:3]
    location = data.get("location")
    location = (str(location).strip() if isinstance(location, (str, int, float)) else "") or "Remote"
    return {"skills": skills, "location": location, "keywords": keywords}


def extract_skills(resume_text: str) -> list[str]:
    return parse_resume(resume_text)["skills"]


def extract_location(resume_text: str) -> str:
    return parse_resume(resume_text)["location"]


def generate_keywords(skills: list[str]) -> list[str]:
    if not skills:
        return ["software developer"]
    obj, _ = _mgr().run_structured(
        "keyword_extract",
        [Message("system", "You return only valid JSON. No markdown."),
         Message("user", f"Given skills: {skills[:15]}\n"
                 'Return ONLY JSON: {"keywords": ["kw1","kw2","kw3"]} with 3-5 job '
                 "search keyword strings.")],
        {"type": "object", "required": ["keywords"],
         "properties": {"keywords": {"type": "array", "items": {"type": "string"}}}},
    )
    kws = obj.get("keywords") if isinstance(obj, dict) else None
    return [str(k).strip() for k in (kws or []) if str(k).strip()] or ["software developer"]


# --------------------------------------------------------------------------- #
# Job reranking (batched)
# --------------------------------------------------------------------------- #
_RERANK_SCHEMA = {
    "type": "object",
    "required": ["results"],
    "properties": {"results": {"type": "array", "items": {
        "type": "object", "required": ["id", "score"],
        "properties": {
            "id": {"type": "integer"}, "score": {"type": "integer"},
            "matched_skills": {"type": "array"}, "missing_skills": {"type": "array"},
            "verdict": {"type": "string"}, "summary": {"type": "string"}},
    }}},
}


def score_jobs_batch(resume_text: str, jobs: list[dict], skills: list[str]) -> list[dict]:
    if not jobs:
        return []
    listings = [
        {"id": i, "title": j.get("title", ""), "company": j.get("company", ""),
         "description": (j.get("description") or j.get("title") or "")[:1200]}
        for i, j in enumerate(jobs)
    ]
    prompt = f"""You are a precise technical recruiter. Score how well each job fits this
candidate, 0-100. Rubric:
- 85-100: meets nearly all core requirements, clear fit
- 65-84: meets most core requirements or strongly transferable
- 40-64: partial / transferable fit, some key gaps
- 15-39: weak fit, mostly different domain
- 0-14: unrelated role
Be discriminating — most jobs should not be 85+.

Return ONLY JSON of shape:
{{"results": [{{"id": 0, "score": 85, "matched_skills": ["Python"],
  "missing_skills": ["Kubernetes"], "verdict": "Strong match",
  "summary": "one specific sentence"}}]}}
verdict must be one of: "Strong match", "Good match", "Partial match", "Weak match".

Candidate skills: {skills[:20]}
Candidate resume:
{resume_text[:1500]}

Jobs:
{json.dumps(listings, ensure_ascii=False)}"""
    try:
        obj, _ = _mgr().run_structured(
            "job_rerank",
            [Message("system", "You return only valid JSON. No markdown."),
             Message("user", prompt)],
            _RERANK_SCHEMA,
        )
    except Exception:
        return []
    results = obj.get("results") if isinstance(obj, dict) else None
    if not isinstance(results, list):
        return []
    out: list[dict] = []
    for pos, item in enumerate(results):
        if isinstance(item, dict):
            if item.get("id") is None:
                item = {**item, "id": pos}
            out.append(item)
    return out


def score_job(resume_text: str, job_description: str, skills: list[str] | None = None,
              title: str = "") -> dict[str, Any]:
    batch = score_jobs_batch(resume_text, [{"title": title, "description": job_description}],
                             skills or [])
    if batch:
        item = batch[0]
        return {"score": int(item.get("score", 0)),
                "matched_skills": item.get("matched_skills", []),
                "missing_skills": item.get("missing_skills", []),
                "verdict": item.get("verdict", ""),
                "summary": item.get("summary", "")}
    return {"score": 0, "matched_skills": [], "summary": "No match."}


# --------------------------------------------------------------------------- #
# Cover letters
# --------------------------------------------------------------------------- #
_COVER_SYSTEM = (
    "You are an expert career writer. You write concise, specific, confident "
    "cover letters in plain prose. No markdown, no placeholders like [Company], "
    "no clichés. 3 short paragraphs, under 220 words."
)


def generate_cover_letter(resume_text: str, title: str, company: str,
                          description: str = "", tone: str = "professional") -> str:
    prompt = f"""Write a {tone} cover letter for this candidate applying to the role below.
Ground it in the candidate's real experience and the job's actual requirements.
Open with genuine interest, make the middle paragraph prove fit with 2-3 concrete
skills/experiences, and close with a call to action. Sign off as the candidate.

ROLE: {title}
COMPANY: {company or "the company"}
JOB DESCRIPTION:
{(description or title)[:1500]}

CANDIDATE RESUME:
{resume_text[:2500]}"""
    result = _mgr().run_task(
        "cover_letter",
        [Message("system", _COVER_SYSTEM), Message("user", prompt)],
    )
    return result.text.strip()
