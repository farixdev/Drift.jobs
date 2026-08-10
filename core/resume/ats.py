"""ATS mechanical checks (Phase 4).

Structural, parser-level checks an applicant-tracking system cares about —
independent of any specific job. Returns a 0..100 score plus a per-check list so
the result is fully explainable.
"""
from __future__ import annotations

import re

_STD_SECTIONS = ("experience", "education", "skills", "summary", "projects",
                 "certification", "work", "employment")


def check_ats(parsed, raw_text: str, filename: str = "") -> dict:
    text = raw_text or ""
    low = text.lower()
    words = re.findall(r"\S+", text)
    n_words = len(words)
    checks: list[dict] = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    contact = parsed.contact or {}
    add("Contact info present", bool(contact.get("email") or contact.get("phone")),
        "email/phone found" if (contact.get("email") or contact.get("phone"))
        else "no email or phone detected")

    # Word-boundary match so 'work' doesn't match 'framework' / 'teamwork', etc.
    sections = [s for s in _STD_SECTIONS if re.search(rf"\b{re.escape(s)}\b", low)]
    add("Standard section headings", len(sections) >= 2,
        f"found: {', '.join(sorted(set(sections))[:5])}" if sections else "no standard headings")

    add("Parseable structure", bool(parsed.experience) or bool(parsed.all_skills()),
        f"{len(parsed.experience)} roles, {len(parsed.all_skills())} skills parsed")

    good_len = 250 <= n_words <= 1200
    add("Reasonable length", good_len,
        f"{n_words} words" + ("" if good_len else " (aim 250–1200)"))

    # Enough extractable text implies text isn't trapped in images/tables.
    add("Text is machine-readable", n_words >= 200,
        "sufficient extractable text" if n_words >= 200
        else "little text — may be image/scanned")

    # File naming: helpful but non-blocking.
    if filename:
        clean = bool(re.match(r"^[\w .\-]+\.(pdf|docx?|txt)$", filename, re.I))
        add("Clean file name", clean, filename if clean else f"'{filename}' has unusual characters")

    passed = sum(1 for c in checks if c["ok"])
    score = round(100 * passed / len(checks)) if checks else 0
    return {"score": score, "checks": checks}
