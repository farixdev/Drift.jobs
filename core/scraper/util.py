"""Shared helpers for scrapers — HTML cleanup, relative dates, keyword filtering."""

import re
from datetime import datetime, timezone

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTINL_RE = re.compile(r"\n{3,}")


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6])>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    text = _WS_RE.sub(" ", text)
    text = _MULTINL_RE.sub("\n\n", text)
    return text.strip()


def human_date(value) -> str:
    """Turn an ISO string or epoch int into a short relative label ('3d ago')."""
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            dt = datetime.fromtimestamp(int(value), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    days = delta.days
    if days < 0:
        return ""
    if days == 0:
        hours = delta.seconds // 3600
        return f"{hours}h ago" if hours else "just now"
    if days == 1:
        return "1d ago"
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    return f"{months}mo ago"


def money(minimum, maximum) -> str:
    """Format a salary range from two numbers, skipping zeros/None."""
    def norm(v):
        try:
            n = int(float(v))
            return n if n > 0 else None
        except (TypeError, ValueError):
            return None

    lo, hi = norm(minimum), norm(maximum)
    if lo and hi:
        return f"${lo:,}–${hi:,}"
    if lo:
        return f"${lo:,}+"
    if hi:
        return f"up to ${hi:,}"
    return ""


def keyword_match(keywords: list[str], *fields: str) -> bool:
    """True when any keyword token appears in the combined text (word-ish match)."""
    tokens = {
        t.lower()
        for kw in keywords
        for t in re.split(r"\s+", (kw or "").strip())
        if len(t) > 2
    }
    if not tokens:
        return True
    haystack = " ".join(f or "" for f in fields).lower()
    return any(tok in haystack for tok in tokens)
