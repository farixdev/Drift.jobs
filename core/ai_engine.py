import json
import re
import time
from typing import Any

from openai import OpenAI

from core.config import get_groq_api_key, get_groq_model

_client: OpenAI | None = None


def has_api_key() -> bool:
    return bool(get_groq_api_key())


def reset_client() -> None:
    """Drop the cached client so a new API key / model takes effect."""
    global _client
    _client = None


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = get_groq_api_key()
    if not api_key:
        from core.config import groq_key_status

        _, message = groq_key_status()
        raise RuntimeError(message)
    _client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    return _client


def _parse_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _chat(
    prompt: str,
    system: str = "You return only valid JSON. No markdown.",
    temperature: float = 0.2,
) -> str:
    delay = 3
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = _get_client().chat.completions.create(
                model=get_groq_model(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            last_error = exc
            msg = str(exc).lower()
            if "429" in msg or "rate" in msg or "quota" in msg:
                if attempt >= 3:
                    raise RuntimeError(
                        "Groq rate limit hit. Wait a minute and try again, "
                        "or use GROQ_MODEL=llama-3.1-8b-instant in .env"
                    ) from exc
                time.sleep(delay)
                delay = min(delay * 2, 45)
                continue
            raise
    raise RuntimeError(f"Groq API error: {last_error}")


def parse_resume(resume_text: str) -> dict[str, Any]:
    prompt = f"""
From this resume return ONLY JSON:
{{
  "skills": ["skill1"],
  "location": "City, Country or Remote",
  "keywords": ["search phrase 1"]
}}

Max 20 skills, 3-5 keywords.

Resume:
{resume_text[:3500]}
"""
    data = _parse_json(_chat(prompt))
    if not isinstance(data, dict):
        data = {}

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
    prompt = f"""
Given skills: {skills[:15]}
Return ONLY a JSON array of 3-5 job search keyword strings.
"""
    return _parse_json(_chat(prompt))


def score_jobs_batch(
    resume_text: str, jobs: list[dict], skills: list[str]
) -> list[dict]:
    if not jobs:
        return []

    listings = [
        {
            "id": i,
            "title": j.get("title", ""),
            "company": j.get("company", ""),
            "description": (j.get("description") or j.get("title") or "")[:1200],
        }
        for i, j in enumerate(jobs)
    ]

    prompt = f"""
You are a precise technical recruiter. Score how well each job fits this
candidate, 0-100. Use this rubric:
- 85-100: meets nearly all core requirements, clear fit
- 65-84: meets most core requirements or strongly transferable
- 40-64: partial / transferable fit, some key gaps
- 15-39: weak fit, mostly different domain
- 0-14: unrelated role
Be discriminating — most jobs should not be 85+. Return ONLY a JSON array, one object per job:
[{{"id": 0, "score": 85, "matched_skills": ["Python","AWS"],
   "missing_skills": ["Kubernetes"], "verdict": "Strong match",
   "summary": "one specific sentence on why it fits or doesn't"}}]

verdict must be one of: "Strong match", "Good match", "Partial match", "Weak match".
matched_skills = candidate skills the job needs. missing_skills = skills the job
asks for that the candidate lacks (max 6).

Candidate skills: {skills[:20]}
Candidate resume:
{resume_text[:1500]}

Jobs:
{json.dumps(listings, ensure_ascii=False)}
"""
    try:
        result = _parse_json(_chat(prompt))
    except (json.JSONDecodeError, ValueError):
        return []

    if isinstance(result, dict):
        result = result.get("jobs") or result.get("results") or result.get("data") or []
    if not isinstance(result, list):
        return []

    normalized: list[dict] = []
    for pos, item in enumerate(result):
        if isinstance(item, dict):
            if item.get("id") is None:
                item = {**item, "id": pos}
            normalized.append(item)
    return normalized


def score_job(
    resume_text: str,
    job_description: str,
    skills: list[str] | None = None,
    title: str = "",
) -> dict[str, Any]:
    batch = score_jobs_batch(
        resume_text,
        [{"title": title, "description": job_description}],
        skills or [],
    )
    if batch:
        item = batch[0]
        return {
            "score": int(item.get("score", 0)),
            "matched_skills": item.get("matched_skills", []),
            "missing_skills": item.get("missing_skills", []),
            "verdict": item.get("verdict", ""),
            "summary": item.get("summary", ""),
        }
    return {"score": 0, "matched_skills": [], "summary": "No match."}


_COVER_SYSTEM = (
    "You are an expert career writer. You write concise, specific, confident "
    "cover letters in plain prose. No markdown, no placeholders like [Company], "
    "no clichés. 3 short paragraphs, under 220 words."
)


def generate_cover_letter(
    resume_text: str,
    title: str,
    company: str,
    description: str = "",
    tone: str = "professional",
) -> str:
    """Draft a tailored cover letter. Requires an API key; caller handles fallback."""
    prompt = f"""
Write a {tone} cover letter for this candidate applying to the role below.
Ground it in the candidate's real experience and the job's actual requirements.
Open with genuine interest, make the middle paragraph prove fit with 2-3 concrete
skills/experiences, and close with a call to action. Sign off as the candidate.

ROLE: {title}
COMPANY: {company or "the company"}
JOB DESCRIPTION:
{(description or title)[:1500]}

CANDIDATE RESUME:
{resume_text[:2500]}
"""
    return _chat(prompt, system=_COVER_SYSTEM, temperature=0.6).strip()
