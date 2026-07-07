"""Hybrid scoring: a free local baseline for every job, refined by the LLM for
the most promising ones. Works fully offline when no API key is set."""

from datetime import datetime
from typing import Callable

from core import ai_engine, local_engine
from core.config import get_max_jobs_to_score
from core.scraper.base import RawJob
from models import Job


def _to_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _merge(local: dict, ai: dict | None) -> dict:
    """LLM result wins on score/verdict/summary; skills are unioned."""
    if not ai:
        return local
    out = dict(local)
    ai_score = _to_int(ai.get("score"))
    if ai_score is not None:
        # LLM judgement leads (0.6) but concrete keyword overlap keeps real
        # weight (0.4) so a transferable role never cliffs to a hard zero even
        # with a weaker judge model.
        ai_score = max(0, min(100, ai_score))
        out["score"] = round(0.6 * ai_score + 0.4 * local.get("score", 0))
    matched = list(dict.fromkeys((ai.get("matched_skills") or []) + local.get("matched_skills", [])))
    out["matched_skills"] = [s for s in matched if s][:8]
    if ai.get("missing_skills"):
        out["missing_skills"] = [s for s in ai["missing_skills"] if s][:8]
    if ai.get("summary"):
        out["summary"] = ai["summary"]
    # Verdict is always derived from the final score so the two never disagree.
    out["verdict"] = local_engine._verdict(out["score"])
    return out


def score_all(
    raw_jobs: list[RawJob],
    resume_text: str,
    skills: list[str] | None = None,
    use_llm: bool | None = None,
    max_llm: int | None = None,
    log: Callable[[str], None] | None = None,
) -> list[Job]:
    if not raw_jobs:
        return []

    skills = skills or local_engine.extract_skills(resume_text)
    if use_llm is None:
        use_llm = ai_engine.has_api_key()
    max_llm = max_llm or get_max_jobs_to_score()

    # Dedupe by fingerprint (belt-and-suspenders on top of per-source dedupe).
    unique: list[RawJob] = []
    seen: set[str] = set()
    for raw in raw_jobs:
        if raw.id in seen:
            continue
        seen.add(raw.id)
        unique.append(raw)

    # 1) Free local baseline for everything.
    scored: list[tuple[RawJob, dict]] = [
        (raw, local_engine.analyze(skills, raw.title, raw.description))
        for raw in unique
    ]
    scored.sort(key=lambda pair: pair[1]["score"], reverse=True)

    # 2) LLM refinement for the most promising N.
    if use_llm and scored:
        top = scored[:max_llm]
        if log:
            log(f"Refining top {len(top)} matches with AI…")
        payloads = [
            {"title": raw.title, "company": raw.company,
             "description": raw.description or raw.title}
            for raw, _ in top
        ]
        try:
            ai_items = ai_engine.score_jobs_batch(resume_text, payloads, skills)
        except Exception as exc:  # network/rate errors → keep local scores
            if log:
                log(f"AI scoring unavailable ({type(exc).__name__}) — using local scores")
            ai_items = []
        by_id = {}
        for pos, item in enumerate(ai_items):
            if isinstance(item, dict):
                idx = _to_int(item.get("id"))
                by_id[idx if idx is not None else pos] = item
        for i, (raw, local) in enumerate(top):
            top[i] = (raw, _merge(local, by_id.get(i)))
        scored[:max_llm] = top
        scored.sort(key=lambda pair: pair[1]["score"], reverse=True)

    # 3) Materialise Job objects (all of them; the UI filters by threshold live).
    jobs: list[Job] = []
    for raw, item in scored:
        jobs.append(
            Job(
                title=raw.title,
                company=raw.company,
                location=raw.location,
                job_type=raw.job_type or "",
                url=raw.url,
                source=raw.source,
                matched_skills=item.get("matched_skills", []),
                missing_skills=item.get("missing_skills", []),
                score=int(item["score"]),
                summary=item.get("summary", ""),
                verdict=item.get("verdict", "") or local_engine._verdict(int(item["score"])),
                salary=raw.salary,
                posted=raw.posted,
                remote=raw.remote,
                scraped_at=datetime.now(),
            )
        )
    return jobs
