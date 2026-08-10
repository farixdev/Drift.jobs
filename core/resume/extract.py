"""Resume parsing → structured schema (Phase 4).

Text extraction stays in core.parser (layout-aware PDF with pdfplumber → pymupdf →
pypdf, DOCX, DOC). On top of it, `extract_structured` uses the AI layer's
schema-validated extraction when a key is present, with a local heuristic fallback
so the app keeps working offline. A parsing error never silently poisons scoring —
it surfaces as a warning and degrades to the local parser.

OCR: if text extraction yields < 200 chars the document is almost certainly a
scanned image. No OCR engine ships with Drift (tesseract isn't a dependency), so
that condition is DETECTED and surfaced as a warning rather than faked — the user
is told to supply a text-based PDF/DOCX. (Honest gate per the spec.)
"""
from __future__ import annotations

from core.resume.schema import RESUME_SCHEMA, ParsedResume

_OCR_THRESHOLD = 200


def extract_text(path: str) -> tuple[str, list[str]]:
    """Return (text, warnings). Never raises for the low-text case — it warns."""
    from core import parser
    warnings: list[str] = []
    try:
        text = parser.extract(path)
    except Exception as exc:
        return "", [f"Could not read the file: {exc}"]
    if len(text.strip()) < _OCR_THRESHOLD:
        warnings.append(
            "Very little text extracted — this looks like a scanned/image PDF. "
            "Drift has no OCR engine; export a text-based PDF or DOCX for full fidelity.")
    return text, warnings


def extract_structured(resume_text: str, *, use_llm: bool | None = None) -> tuple[ParsedResume, list[str]]:
    """Return (ParsedResume, warnings). LLM extraction when available, else local."""
    warnings: list[str] = []
    text = (resume_text or "").strip()
    if len(text) < 20:
        return ParsedResume(), ["Resume text too short to parse."]

    if use_llm is None:
        from core import ai_engine
        use_llm = ai_engine.has_api_key()

    if use_llm:
        try:
            return _llm_extract(text), warnings
        except Exception as exc:
            warnings.append(f"AI extraction failed ({type(exc).__name__}) — using local parser.")
    return _local_extract(text), warnings


def _llm_extract(text: str) -> ParsedResume:
    from core.ai import LLMManager, Message
    prompt = (
        "Extract this resume into the given JSON schema. Extract ONLY what is "
        "actually written — never invent employers, titles, dates, degrees, "
        "certifications, or skills that are not present. Omit fields you cannot find.\n\n"
        f"RESUME:\n{text[:7000]}"
    )
    obj, _ = LLMManager().run_structured(
        "resume_parse",
        [Message("system", "You extract structured data faithfully. Never fabricate."),
         Message("user", prompt)],
        RESUME_SCHEMA,
    )
    parsed = ParsedResume.from_dict(obj if isinstance(obj, dict) else {})
    _backfill_local(parsed, text)
    return parsed


def _backfill_local(parsed: ParsedResume, text: str) -> None:
    """Safety net: fill contact + technical skills from the deterministic local
    parser where the model left them empty. Never overwrites model data; only
    fills gaps, and never fabricates (local extraction is grounded in the text)."""
    from core import local_engine
    if not (parsed.contact or {}).get("email") or not (parsed.contact or {}).get("location"):
        local = _local_extract(text)
        merged = dict(local.contact)
        merged.update({k: v for k, v in (parsed.contact or {}).items() if v})
        parsed.contact = merged
    tech = list(parsed.skills.get("technical") or [])
    if not tech:  # only when the model returned none — don't second-guess a real list
        have = {t.lower() for t in tech}
        for s in local_engine.extract_skills(text):
            if s.lower() not in have:
                tech.append(s)
                have.add(s.lower())
        parsed.skills["technical"] = tech


def _local_extract(text: str) -> ParsedResume:
    """Heuristic, key-free fallback: skills via the local vocab + regex contact.
    Lower fidelity (no structured experience), but never fabricates."""
    import re

    from core import local_engine
    contact = {}
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if m:
        contact["email"] = m.group(0)
    m = re.search(r"(?:(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})", text)
    if m:
        contact["phone"] = m.group(0)
    contact["location"] = local_engine.extract_location(text)
    # name: first non-empty line that isn't an email/heading
    for line in text.splitlines():
        line = line.strip()
        if line and "@" not in line and len(line.split()) <= 5 and line[0].isalpha():
            contact.setdefault("name", line[:60])
            break
    links = re.findall(r"https?://[^\s)]+", text)
    tech = local_engine.extract_skills(text)
    return ParsedResume(
        contact=contact,
        skills={"technical": tech, "soft": [], "tools": [], "languages": []},
        links=links[:10],
    )
