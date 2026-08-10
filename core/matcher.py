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


def _as_list(value) -> list[str]:
    """LLMs often return skill fields as a comma-string instead of an array."""
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def _align(ai_items: list, n: int) -> dict[int, dict]:
    """Map AI results to sent jobs. Trust returned ids only when they form a
    valid unique permutation of 0..n-1; otherwise fall back to positional order
    (so a model that renumbers or drops items can't misassign one job's analysis
    to another)."""
    items = [it for it in ai_items if isinstance(it, dict)]
    ids = [_to_int(it.get("id")) for it in items]
    valid = (
        len(items) == n
        and all(i is not None and 0 <= i < n for i in ids)
        and len(set(ids)) == len(ids)
    )
    if valid:
        return {i: it for i, it in zip(ids, items)}
    return {pos: it for pos, it in enumerate(items) if pos < n}


def _merge(local: dict, ai: dict | None) -> dict:
    """The calibrated local score is the backbone; the LLM verdict can LIFT it
    freely (a confident high AI score is usually right) but can only pull it DOWN
    within a bounded band — so a weak judge model can't nuke a genuine match to
    zero. The LLM also supplies the summary + gap analysis."""
    if not ai:
        return local
    out = dict(local)
    local_score = local.get("score", 0)
    ai_score = _to_int(ai.get("score"))
    if ai_score is not None:
        ai_score = max(0, min(100, ai_score))
        if ai_score >= local_score:  # AI more optimistic → trust it
            out["score"] = round(0.7 * ai_score + 0.3 * local_score)
        else:  # AI more pessimistic → bounded downward correction only
            out["score"] = max(round(0.5 * ai_score + 0.5 * local_score), local_score - 20)
        out["score"] = max(0, min(100, out["score"]))
    matched = list(dict.fromkeys(_as_list(ai.get("matched_skills")) + local.get("matched_skills", [])))
    out["matched_skills"] = [s for s in matched if s][:8]
    ai_missing = _as_list(ai.get("missing_skills"))
    if ai_missing:
        out["missing_skills"] = ai_missing[:8]
    if isinstance(ai.get("summary"), str) and ai["summary"].strip():
        out["summary"] = ai["summary"].strip()
    # Verdict is always derived from the final score so the two never disagree.
    out["verdict"] = local_engine._verdict(out["score"])
    return out


def score_all(
    raw_jobs: list[RawJob],
    resume_text: str,
    skills: list[str] | None = None,
    use_llm: bool | None = None,
    max_llm: int | None = None,
    keywords: list[str] | None = None,
    log: Callable[[str], None] | None = None,
    meta_by_id: dict | None = None,
) -> list[Job]:
    if not raw_jobs:
        return []

    skills = skills or local_engine.extract_skills(resume_text)
    if use_llm is None:
        use_llm = ai_engine.has_api_key()
    max_llm = max_llm or get_max_jobs_to_score()
    terms = local_engine.role_terms(keywords or [], skills)

    # Dedupe by fingerprint (belt-and-suspenders on top of per-source dedupe).
    unique: list[RawJob] = []
    seen: set[str] = set()
    for raw in raw_jobs:
        if raw.id in seen:
            continue
        seen.add(raw.id)
        unique.append(raw)

    # Drop feed noise (roles with no plausible overlap) before spending scoring.
    relevant = [
        raw for raw in unique
        if local_engine.is_relevant(skills, terms, raw.title, raw.description)
    ]
    if relevant:
        dropped = len(unique) - len(relevant)
        if dropped and log:
            log(f"Filtered {dropped} off-target listing(s)")
        unique = relevant
    # else: nothing looked relevant — keep everything rather than show nothing.

    # 1) Free local baseline for everything.
    scored: list[tuple[RawJob, dict]] = [
        (raw, local_engine.analyze(skills, raw.title, raw.description, terms))
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
        by_id = _align(ai_items, len(top))
        for i, (raw, local) in enumerate(top):
            try:
                top[i] = (raw, _merge(local, by_id.get(i)))
            except Exception:  # one malformed AI item must not kill the whole scan
                top[i] = (raw, local)
        scored[:max_llm] = top
        scored.sort(key=lambda pair: pair[1]["score"], reverse=True)

    # 3) Materialise Job objects (all of them; the UI filters by threshold live).
    meta_by_id = meta_by_id or {}
    jobs: list[Job] = []
    for raw, item in scored:
        meta = meta_by_id.get(raw.id, {})
        jobs.append(
            Job(
                title=raw.title,
                company=raw.company,
                location=raw.location,
                job_type=raw.job_type or "",
                url=raw.url,
                source=raw.source,
                description=(raw.description or "")[:4000],
                matched_skills=item.get("matched_skills", []),
                missing_skills=item.get("missing_skills", []),
                score=int(item["score"]),
                summary=item.get("summary", ""),
                verdict=item.get("verdict", "") or local_engine._verdict(int(item["score"])),
                salary=raw.salary,
                posted=raw.posted,
                remote=raw.remote,
                scraped_at=datetime.now(),
                fingerprint=meta.get("fingerprint", ""),
                alt_urls=meta.get("alt_urls", []),
                seen_count=meta.get("seen_count", 1),
            )
        )
    return jobs
