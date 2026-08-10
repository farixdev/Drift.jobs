"""Field-level normalizers: salary, dates, location, employment/seniority, company.

All pure and deterministic. The guiding rule (Phase 8): normalize only what the
source actually states — never infer a salary that isn't there, never guess a
country we can't read. Absent data stays null/empty, honestly.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------- #
# Salary
# --------------------------------------------------------------------------- #
_CUR = {"$": "USD", "£": "GBP", "€": "EUR", "usd": "USD", "gbp": "GBP",
        "eur": "EUR", "cad": "CAD", "aud": "AUD"}
_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kK]?)"
_PERIOD = [(r"per\s*hour|/\s*hour|/\s*hr|hourly|/hr", "hour"),
           (r"per\s*day|/\s*day|daily", "day"),
           (r"per\s*month|/\s*month|monthly|/mo", "month"),
           (r"per\s*year|/\s*year|annual|annually|/yr|/year", "year")]


def parse_salary(text: str) -> dict:
    """Return {min,max,currency,period,is_estimated}. All None if unparseable.

    is_estimated is True ONLY when the source text says so — we never infer it.
    """
    out = {"min": None, "max": None, "currency": "", "period": "", "is_estimated": False}
    if not text or not text.strip():
        return out
    s = text.strip()
    low = s.lower()

    # currency
    for sym, code in _CUR.items():
        if sym in low:
            out["currency"] = code
            break

    # numbers (with optional k)
    nums = []
    for m in re.finditer(_NUM, s):
        val = float(m.group(1).replace(",", ""))
        if m.group(2).lower() == "k":
            val *= 1000
        nums.append(int(val))
    nums = [n for n in nums if n >= 1000 or (out["currency"] and n >= 5)]  # drop noise
    if not nums:
        return out
    if len(nums) == 1:
        # "up to X" / "from X"
        if re.search(r"up to|max", low):
            out["max"] = nums[0]
        else:
            out["min"] = nums[0]
    else:
        out["min"], out["max"] = min(nums[0], nums[1]), max(nums[0], nums[1])

    for pat, period in _PERIOD:
        if re.search(pat, low):
            out["period"] = period
            break
    if not out["period"] and (out["min"] or out["max"]):
        hi = out["max"] or out["min"]
        out["period"] = "hour" if hi and hi < 1000 else "year"

    if re.search(r"estimat|approx|~", low):
        out["is_estimated"] = True
    return out


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #
_REL = re.compile(r"(?i)(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago")
_UNIT = {"second": "seconds", "minute": "minutes", "hour": "hours", "day": "days",
         "week": "weeks"}


def parse_posted(value, *, now: datetime | None = None) -> dict:
    """Return {iso, is_approximate}. iso is UTC ISO-8601 or None.

    Relative strings ('3 days ago') are computed and marked approximate.
    """
    now = now or datetime.now(timezone.utc)
    out = {"iso": None, "is_approximate": False}
    if value is None or value == "":
        return out

    # epoch (int/str of digits) or epoch-ms
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        ts = int(value)
        if ts > 10_000_000_000:  # milliseconds
            ts //= 1000
        try:
            out["iso"] = datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat()
        except (OSError, OverflowError, ValueError):
            pass
        return out

    s = str(value).strip()
    low = s.lower()
    if low in ("just now", "today", "just posted"):
        out["iso"] = now.replace(microsecond=0).isoformat()
        out["is_approximate"] = True
        return out
    if low in ("yesterday",):
        out["iso"] = (now - timedelta(days=1)).replace(microsecond=0).isoformat()
        out["is_approximate"] = True
        return out

    m = _REL.search(s)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        if unit == "month":
            delta = timedelta(days=30 * n)
        elif unit == "year":
            delta = timedelta(days=365 * n)
        else:
            delta = timedelta(**{_UNIT[unit]: n})
        out["iso"] = (now - delta).replace(microsecond=0).isoformat()
        out["is_approximate"] = True
        return out

    # ISO-ish
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        out["iso"] = dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        pass
    return out


# --------------------------------------------------------------------------- #
# Location
# --------------------------------------------------------------------------- #
_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}
_COUNTRIES = {
    "usa","us","united states","uk","united kingdom","canada","germany","france",
    "spain","italy","netherlands","ireland","poland","portugal","sweden","norway",
    "denmark","finland","switzerland","austria","belgium","australia","india",
    "singapore","japan","brazil","mexico","pakistan","hungary",
}
_REMOTE = re.compile(r"(?i)\b(remote|work from home|wfh|anywhere|distributed)\b")
_HYBRID = re.compile(r"(?i)\bhybrid\b")
_ONSITE = re.compile(r"(?i)\b(on[\s-]?site|in[\s-]?office)\b")


def parse_location(text: str, *, remote_flag: bool | None = None) -> dict:
    """Return {city, region, country, work_mode}. work_mode uses the controlled
    vocab remote|hybrid|onsite|unspecified."""
    out = {"city": "", "region": "", "country": "", "work_mode": "unspecified"}
    t = (text or "").strip()
    if remote_flag or (t and _REMOTE.search(t)):
        out["work_mode"] = "remote"
    elif t and _HYBRID.search(t):
        out["work_mode"] = "hybrid"
    elif t and _ONSITE.search(t):
        out["work_mode"] = "onsite"

    # strip parenthetical hints and remote words, then split on commas
    cleaned = re.sub(r"\([^)]*\)", "", t)
    cleaned = _REMOTE.sub("", cleaned)
    cleaned = _HYBRID.sub("", cleaned)
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if parts:
        last = parts[-1]
        if last.lower() in _COUNTRIES:
            out["country"] = last
            parts = parts[:-1]
        if parts:
            cand = parts[-1]
            if cand.upper() in _US_STATES:
                out["region"] = cand.upper()
                if not out["country"]:
                    out["country"] = "USA"
                parts = parts[:-1]
            elif len(parts) >= 2:
                out["region"] = cand
                parts = parts[:-1]
        if parts:
            out["city"] = parts[0]
    return out


# --------------------------------------------------------------------------- #
# Employment type + seniority (controlled vocab)
# --------------------------------------------------------------------------- #
_EMPLOYMENT = {
    "full-time": "full_time", "fulltime": "full_time", "full time": "full_time",
    "permanent": "full_time", "part-time": "part_time", "parttime": "part_time",
    "part time": "part_time", "contract": "contract", "contractor": "contract",
    "freelance": "freelance", "temporary": "temporary", "temp": "temporary",
    "internship": "internship", "intern": "internship",
}
_SENIORITY = [
    (r"\b(intern|internship)\b", "intern"),
    (r"\b(principal|staff|distinguished|fellow)\b", "principal"),
    (r"\b(senior|sr\.?|lead|head of|director|vp|chief)\b", "senior"),
    (r"\b(junior|jr\.?|entry|associate|graduate|new grad)\b", "junior"),
    (r"\b(mid|intermediate)\b", "mid"),
]


def normalize_employment(text: str) -> str:
    low = (text or "").lower().strip()
    for key, val in _EMPLOYMENT.items():
        if key in low:
            return val
    return ""


def infer_seniority(title: str, employment_type: str = "") -> str:
    t = (title or "").lower()
    for pat, level in _SENIORITY:
        if re.search(pat, t):
            return level
    if employment_type == "internship":
        return "intern"
    return ""


# --------------------------------------------------------------------------- #
# Company
# --------------------------------------------------------------------------- #
_SUFFIX = re.compile(r"(?i)[\s,]+(inc|inc\.|llc|ltd|ltd\.|gmbh|corp|corporation|"
                     r"co|co\.|company|plc|group|holdings|technologies|labs)\.?$")
_YC = re.compile(r"(?i)\s*\(yc\s+\w+\)")


def canonical_company(name: str) -> str:
    n = (name or "").strip()
    n = _YC.sub("", n)
    prev = None
    while prev != n:  # strip stacked suffixes ("Foo Technologies Inc")
        prev = n
        n = _SUFFIX.sub("", n).strip(" ,.-")
    return n or (name or "").strip()


def company_key(name: str) -> str:
    """Aggressive normalized key for dedup: lowercase alnum of the canonical name."""
    return re.sub(r"[^a-z0-9]", "", canonical_company(name).lower())
