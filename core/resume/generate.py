"""Tailored resume + gap report generation (Phase 4).

HARD RULE: generation never invents employers, titles, dates, credentials, or
metrics — it only rephrases what already exists to surface honestly-matched
keywords. This is enforced three ways:
  1. the system prompt forbids fabrication,
  2. a post-generation safety check reverts any rewrite that introduces a number
     not present in the original bullet (fabricated metric), flagging it, and
  3. every changed bullet is returned as a diff for explicit user approval before
     anything is saved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_NUM = re.compile(r"\d[\d,.]*%?")


@dataclass
class BulletDiff:
    role: str
    original: str
    rewritten: str
    changed: bool
    flagged: bool = False        # safety check tripped (kept original)
    flag_reason: str = ""


_NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight",
                 "nine", "ten", "hundred", "thousand", "million", "billion",
                 "dozen", "double", "triple", "quadrupled", "doubled", "tripled"}


def _numbers(text: str) -> set[str]:
    nums = {n.replace(",", "").rstrip("%.") for n in _NUM.findall(text or "")}
    # Catch spelled-out quantities too ("five million") so a fabricated metric
    # can't slip past by avoiding ASCII digits.
    words = {w for w in re.findall(r"[a-z]+", (text or "").lower()) if w in _NUMBER_WORDS}
    return {n for n in nums if n} | words


def _safe_rewrite(original: str, rewritten: str, allowed_skills: set | None = None) -> tuple[str, bool, str]:
    """Accept a rewrite only if it invents nothing:
    - no numbers/metrics absent from the original bullet, and
    - no technology/skill that is neither in the original bullet nor anywhere in
      the candidate's résumé (surfacing a skill they genuinely have is fine;
      inventing one they don't is not)."""
    if not rewritten.strip():
        return original, True, "empty rewrite"
    new_nums = _numbers(rewritten) - _numbers(original)
    if new_nums:
        return original, True, f"introduced metric(s) not in original: {', '.join(sorted(new_nums))}"

    from core import local_engine
    from core.skills_db import TECH_SKILLS
    allowed = allowed_skills or set()
    # Strip only sentence punctuation at token boundaries (before whitespace/end),
    # so a trailing '.' doesn't hide a match while dotted skills (.net, node.js,
    # next.js) stay intact and remain detectable if invented.
    orig_n = _PUNCT.sub(" ", original)
    new_n = _PUNCT.sub(" ", rewritten)
    invented = [s for s in TECH_SKILLS
                if local_engine._contains_skill(new_n, s)
                and not local_engine._contains_skill(orig_n, s)
                and s.lower() not in allowed]
    if invented:
        return original, True, f"introduced skill(s) not in résumé: {', '.join(invented[:4])}"
    # NOTE: the automated guard catches invented numbers/metrics and invented
    # skills. Purely qualitative invention (a fake employer name, an inflated
    # scope/seniority claim) can't be detected mechanically — the diff-approval
    # UI, where the user reviews every changed bullet, is the backstop for that.
    return rewritten.strip(), False, ""


# Punctuation only at a token boundary — preserves in-token dots like ".net".
_PUNCT = re.compile(r"[.,;:!?()\[\]{}](?=\s|$)")


def tailor_bullets(parsed, job: dict, *, use_llm: bool | None = None) -> list[BulletDiff]:
    """Rewrite each experience bullet to surface job-relevant keywords honestly.
    Returns a diff per bullet for approval. Falls back to no-op (originals) when
    no LLM is available."""
    bullets: list[tuple[str, str]] = []  # (role, bullet)
    for e in parsed.experience or []:
        role = f"{e.title} — {e.company}".strip(" —")
        for b in e.bullets or []:
            bullets.append((role, b))
    if not bullets:
        return []

    if use_llm is None:
        from core import ai_engine
        use_llm = ai_engine.has_api_key()
    if not use_llm:
        return [BulletDiff(role=r, original=b, rewritten=b, changed=False) for r, b in bullets]

    from core.ai import LLMManager, Message
    from core.ai.jsonutil import validate

    listing = [{"id": i, "bullet": b} for i, (_, b) in enumerate(bullets)]
    jd = f"{job.get('title','')}\n{(job.get('description','') or '')[:1500]}"
    prompt = (
        "Rewrite each résumé bullet to better surface skills and keywords relevant "
        "to the job below — but you MUST NOT invent anything. Do not add employers, "
        "titles, dates, technologies, or metrics/numbers that are not already in the "
        "original bullet. Only rephrase what is there. If a bullet is already good, "
        "return it unchanged.\n\n"
        f"JOB:\n{jd}\n\n"
        f"BULLETS (JSON):\n{listing}\n\n"
        'Return ONLY JSON: {"bullets":[{"id":0,"rewritten":"..."}]}'
    )
    schema = {"type": "object", "required": ["bullets"], "properties": {"bullets": {
        "type": "array", "items": {"type": "object", "required": ["id", "rewritten"],
        "properties": {"id": {"type": "integer"}, "rewritten": {"type": "string"}}}}}}
    try:
        obj, _ = LLMManager().run_structured(
            "resume_tailor",
            [Message("system", "You rephrase résumé bullets truthfully. You never fabricate."),
             Message("user", prompt)], schema)
        items = {int(it["id"]): it.get("rewritten", "")
                 for it in obj.get("bullets", []) if isinstance(it, dict) and "id" in it}
    except Exception:
        items = {}

    # Skills the candidate genuinely has — legitimately surfaceable into bullets.
    allowed = {s.lower() for s in parsed.all_skills()}
    for grp in ("technical", "tools", "languages"):
        allowed |= {str(s).lower() for s in (parsed.skills or {}).get(grp, [])}

    diffs: list[BulletDiff] = []
    for i, (role, original) in enumerate(bullets):
        proposed = items.get(i, original)
        final, flagged, reason = _safe_rewrite(original, proposed, allowed)
        diffs.append(BulletDiff(role=role, original=original, rewritten=final,
                                changed=(final.strip() != original.strip()),
                                flagged=flagged, flag_reason=reason))
    return diffs


def gap_report(rubric_result: dict) -> dict:
    """What the candidate would need to add or learn to clear the role."""
    missing = rubric_result.get("missing", [])
    weak = [k for k, d in rubric_result.get("dimensions", {}).items()
            if d.get("score") is not None and d["score"] < 50]
    return {
        "missing": missing,
        "weak_dimensions": weak,
        "summary": ("You're close." if not missing else
                    f"To strengthen this application, address: {', '.join(missing[:5])}."),
    }
