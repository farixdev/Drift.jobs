"""Canonicalize apply/listing URLs before fingerprinting.

Strips tracking params (utm_*, gh_src, gclid, …), lowercases the host, drops the
fragment and trailing slash, so `boards.greenhouse.io/co/jobs/123?gh_src=xyz` and
the same URL shared from elsewhere collapse to one canonical form.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "gh_jid_src", "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
    "ref", "referrer", "source", "src", "_hsenc", "_hsmi", "trk", "trackingId",
    "lever-source", "lever-origin", "utm_id",
}


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    if not p.netloc:
        return url.strip()
    kept = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
            if k.lower() not in _TRACKING]
    path = p.path.rstrip("/") or p.path
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path,
                       p.params, urlencode(kept), ""))  # fragment dropped
