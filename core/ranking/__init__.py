"""Hybrid three-stage ranking (Phase 8): lexical → semantic → LLM rerank.

    rank_jobs(normalized_jobs, resume_text, skills, keywords) -> [Job]

1. Lexical BM25 over every candidate (cheap).
2. Semantic cosine similarity of embeddings (cached; skipped if no embedder).
3. LLM rerank the top 100 by stages 1+2, batched 20/call, returning a score and a
   one-sentence rationale.

The final score blends the available stages by user-adjustable weights, multiplied
by a freshness decay and filtered against the blocklist. Every Job carries its
per-dimension sub-scores + rationale, so the card can always explain the number —
if a job can't be explained it isn't shown (it always can: lexical + freshness).
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from core import local_engine
from core.ranking import blend, lexical, semantic
from models import Job

_RERANK_TOP = 100
_display = None  # lazy


def _fmt(nj) -> dict:
    from core.scraper.util import human_date, money
    sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(nj.salary_currency, "$")
    salary = money(nj.salary_min, nj.salary_max).replace("$", sym) \
        if (nj.salary_min or nj.salary_max) else ""
    return {
        "location": nj.location_raw or nj.location_city
        or ("Remote" if nj.work_mode == "remote" else ""),
        "salary": salary,
        "posted": human_date(nj.posted_at) if nj.posted_at else "",
    }


def rank_jobs(normalized: list, resume_text: str, skills: list[str] | None = None,
              keywords: list[str] | None = None, *, use_llm: bool | None = None,
              log: Callable[[str], None] | None = None) -> list[Job]:
    if not normalized:
        return []
    skills = skills or []
    terms = local_engine.role_terms(keywords or [], skills)
    query_terms = list(dict.fromkeys((keywords or []) + skills))

    # Stage 1 — lexical
    docs = [f"{nj.title} {nj.description_text}" for nj in normalized]
    lex = lexical.bm25_scores(docs, query_terms)

    # Stage 2 — semantic (or None if no embedder)
    sem = semantic.semantic_scores(resume_text, normalized)
    has_sem = sem is not None
    if log:
        log("Semantic ranking on" if has_sem else "Semantic ranking off (no embedder)")

    # Pick the top N for the expensive LLM stage by the combined 1+2 signal.
    prelim = [(0.4 * lex[i] + 0.6 * sem[i]) if has_sem else lex[i]
              for i in range(len(normalized))]
    order = sorted(range(len(normalized)), key=lambda i: prelim[i], reverse=True)
    top = order[:_RERANK_TOP]

    # matched/missing skills for every job (transparent gap analysis)
    analyses = [local_engine.analyze(skills, nj.title, nj.description_text, terms)
                for nj in normalized]

    # Stage 3 — LLM rerank the top N
    llm: list[float | None] = [None] * len(normalized)
    rationale: list[str] = [""] * len(normalized)
    if use_llm is None:
        from core import ai_engine
        use_llm = ai_engine.has_api_key()
    if use_llm and top:
        from core import ai_engine
        from core.matcher import _align
        payloads = [{"title": normalized[i].title, "company": normalized[i].company_name,
                     "description": normalized[i].description_text or normalized[i].title}
                    for i in top]
        if log:
            log(f"LLM rerank of top {len(payloads)} matches…")
        try:
            ai_items = ai_engine.score_jobs_batch(resume_text, payloads, skills)
        except Exception:
            ai_items = []
        by_pos = _align(ai_items, len(top))
        for k, i in enumerate(top):
            item = by_pos.get(k)
            if item:
                llm[i] = max(0, min(100, int(item.get("score", 0)))) / 100.0
                rationale[i] = (item.get("summary") or "").strip()

    w = blend.weights()
    bl = blend.load_blocklist()
    jobs: list[Job] = []
    for i, nj in enumerate(normalized):
        parts = [("lexical", lex[i], w.get("lexical", 0.25))]
        if has_sem:
            parts.append(("semantic", sem[i], w.get("semantic", 0.30)))
        if llm[i] is not None:
            parts.append(("llm", llm[i], w.get("llm", 0.45)))
        tot_w = sum(p[2] for p in parts) or 1.0
        base = sum(p[1] * p[2] for p in parts) / tot_w
        fresh = blend.freshness_factor(nj.posted_at)
        final = int(round(base * 100 * fresh))

        subs = {"lexical": round(lex[i] * 100)}
        if has_sem:
            subs["semantic"] = round(sem[i] * 100)
        if llm[i] is not None:
            subs["llm"] = round(llm[i] * 100)
        subs["freshness"] = round(fresh, 2)

        d = _fmt(nj)
        a = analyses[i]
        job = Job(
            title=nj.title, company=nj.company_name, location=d["location"],
            job_type=nj.employment_type, url=nj.canonical_url or nj.apply_url,
            source=nj.source, description=(nj.description_text or "")[:4000],
            matched_skills=a.get("matched_skills", []),
            missing_skills=a.get("missing_skills", []),
            score=max(0, min(100, final)),
            summary=rationale[i] or a.get("summary", ""),
            verdict=local_engine._verdict(max(0, min(100, final))),
            salary=d["salary"], posted=d["posted"],
            remote=(nj.work_mode == "remote"), scraped_at=datetime.now(),
            fingerprint=nj.fingerprint, alt_urls=nj.alt_urls, seen_count=nj.seen_count,
            subscores=subs, rationale=rationale[i],
        )
        if blend.is_blocked(job, bl):
            continue
        jobs.append(job)

    jobs.sort(key=lambda j: j.score, reverse=True)
    return jobs


__all__ = ["rank_jobs"]
