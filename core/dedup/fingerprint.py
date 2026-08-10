"""Content-based job fingerprint (Phase 8) — replaces the 1.x URL hash.

Identity = normalize(company) + normalize(title) + normalize(city), so the same
role posted to fifteen boards collapses to ONE record. simhash(description) is
carried alongside for the clusterer to merge title/formatting variants.

This is the destructive identity change flagged in the audit (§9.4b); migration
m005 recomputes every stored fingerprint and keeps an alias table.
"""
from __future__ import annotations

import hashlib
import re

from core.normalize.fields import company_key

_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^a-z0-9]+")


def title_key(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"\([^)]*\)", " ", t)          # drop parentheticals
    t = _NONWORD.sub(" ", t)
    return _WS.sub(" ", t).strip()


def city_key(city: str) -> str:
    return _NONWORD.sub("", (city or "").lower())


def content_fingerprint(company: str, title: str, city: str) -> str:
    basis = f"{company_key(company)}|{title_key(title)}|{city_key(city)}"
    return hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()[:16]
