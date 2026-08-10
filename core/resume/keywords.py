"""Keyword intelligence (Phase 4): weighted skills, synonym expansion, target
detection — the bridge between the resume and the search builder / ranking.
"""
from __future__ import annotations

import re

from core.normalize.fields import infer_seniority

# Synonym / variant groups. Any member expands to the whole group so a search for
# "k8s" also matches "Kubernetes" (and vice-versa). Bidirectional.
_GROUPS = [
    ["kubernetes", "k8s"],
    ["javascript", "js"],
    ["typescript", "ts"],
    ["postgresql", "postgres", "psql"],
    ["python", "py"],
    ["golang", "go"],
    ["react", "reactjs", "react.js"],
    ["node.js", "nodejs", "node"],
    ["amazon web services", "aws"],
    ["google cloud platform", "gcp"],
    ["microsoft azure", "azure"],
    ["ci/cd", "cicd", "continuous integration"],
    ["machine learning", "ml"],
    ["artificial intelligence", "ai"],
    ["natural language processing", "nlp"],
    ["registered nurse", "rn"],
    ["c++", "cpp"],
    ["c#", "csharp", "c sharp"],
    ["rest api", "rest", "restful"],
    ["infrastructure as code", "iac", "terraform"],
    ["object oriented programming", "oop"],
    ["user interface", "ui"],
    ["user experience", "ux"],
    ["quality assurance", "qa"],
    ["software development kit", "sdk"],
]

_SYNONYMS: dict[str, set[str]] = {}
for _g in _GROUPS:
    members = set(_g)
    for _m in _g:
        _SYNONYMS.setdefault(_m.lower(), set()).update(members)


def expand_term(term: str) -> list[str]:
    """A term plus its known variants (deduped, original first)."""
    key = (term or "").strip().lower()
    variants = _SYNONYMS.get(key, set())
    out = [term]
    for v in sorted(variants):
        if v != key:
            out.append(v)
    return list(dict.fromkeys(out))


def expansion_map(terms: list[str]) -> dict[str, list[str]]:
    """{term: [variants...]} for the terms that actually have synonyms — stored so
    search queries can widen with them (Phase 5/6 bridge)."""
    out: dict[str, list[str]] = {}
    for t in terms:
        exp = expand_term(t)
        if len(exp) > 1:
            out[t] = exp
    return out


def weighted_skills(parsed) -> list[tuple[str, float]]:
    """Skills with weights: technical > certifications > tools > spoken languages."""
    skills = parsed.skills or {}
    out: list[tuple[str, float]] = []
    seen: set[str] = set()

    def add(items, weight):
        for s in items or []:
            k = str(s).strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append((str(s).strip(), weight))

    add(skills.get("technical"), 1.0)
    add(parsed.certifications, 0.9)
    add(skills.get("tools"), 0.7)
    add(skills.get("languages"), 0.3)
    return out


def _parse_year(s: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def years_experience(parsed) -> float:
    """Rough total years from experience start/end (present → now)."""
    import datetime
    now_year = 2026  # avoids nondeterminism in tests; refined below if datetime ok
    try:
        now_year = datetime.date.today().year
    except Exception:
        pass
    total = 0.0
    for e in parsed.experience or []:
        start = _parse_year(e.start)
        end = _parse_year(e.end) or (now_year if re.search(r"(?i)present|current", e.end or "")
                                     else None)
        if start and end and end >= start:
            total += end - start
    if total == 0:
        # Fallback: an explicit "N years" claim in the summary (models often omit
        # the per-role dates the year computation needs).
        m = re.search(r"(\d{1,2})\s*\+?\s*years?", parsed.summary or "", re.I)
        if m:
            total = float(m.group(1))
    return round(total, 1)


def target_titles(parsed, include_variants: bool = True) -> list[str]:
    """Editable target-title suggestions from the most recent roles."""
    titles = [e.title.strip() for e in (parsed.experience or []) if e.title.strip()]
    out: list[str] = []
    for t in titles[:3]:
        if t not in out:
            out.append(t)
    if include_variants and out:
        base = re.sub(r"(?i)\b(senior|junior|lead|staff|principal|sr\.?|jr\.?)\b", "", out[0]).strip()
        for pref in ("Senior", ""):
            cand = f"{pref} {base}".strip()
            if cand and cand not in out:
                out.append(cand)
    return out[:5]


def seniority_band(parsed) -> str:
    titles = [e.title for e in (parsed.experience or []) if e.title]
    for t in titles:
        band = infer_seniority(t)
        if band:
            return band
    yrs = years_experience(parsed)
    if yrs >= 8:
        return "senior"
    if yrs >= 3:
        return "mid"
    if yrs > 0:
        return "junior"
    return ""
