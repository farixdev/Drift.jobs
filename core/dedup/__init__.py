"""Deduplication + clustering (Phase 8).

Groups normalized jobs that are the same role posted to multiple boards, keeps the
most complete + most authoritative record (direct ATS > aggregator > feed), stores
every alternate apply URL on the cluster, and stamps a `seen_count` for the
"seen on N sites" badge.

Clustering: primary grouping is the content fingerprint (company+title+city).
Within the resulting set, buckets that share a company+city and have near-identical
descriptions (simhash Hamming ≤ 3) are merged, catching title/formatting variants
the fingerprint alone would miss.
"""
from __future__ import annotations

from core.dedup.fingerprint import content_fingerprint, title_key
from core.dedup.simhash import near
from core.normalize.fields import company_key  # fields has no dedup dependency


def _more_complete(a, b):
    """Pick the better canonical record: authority, then completeness."""
    def score(j):
        return (j.authority,
                1 if (j.salary_min or j.salary_max) else 0,
                1 if j.location_city else 0,
                len(j.description_text))
    return a if score(a) >= score(b) else b


def cluster(normalized: list) -> list:
    """Collapse duplicates. Returns one canonical NormalizedJob per real role,
    each carrying seen_count, alt_urls, and the set of sources it appeared on."""
    # 1) exact grouping by content fingerprint
    groups: dict[str, list] = {}
    for j in normalized:
        groups.setdefault(j.fingerprint, []).append(j)

    reps: list[list] = list(groups.values())

    # 2) merge near-duplicate groups (same company+city, near description)
    merged: list[list] = []
    for grp in reps:
        head = grp[0]
        hit = None
        for m in merged:
            mh = m[0]
            if (company_key(head.company_name) == company_key(mh.company_name)
                    and head.location_city.lower() == mh.location_city.lower()
                    and near(head.simhash, mh.simhash, threshold=3)):
                hit = m
                break
        if hit is not None:
            hit.extend(grp)
        else:
            merged.append(list(grp))

    out: list[NormalizedJob] = []
    for grp in merged:
        canonical = grp[0]
        for other in grp[1:]:
            canonical = _more_complete(canonical, other)
        urls, sources = [], []
        for j in grp:
            if j.canonical_url and j.canonical_url not in urls:
                urls.append(j.canonical_url)
            for s in j.sources:
                if s not in sources:
                    sources.append(s)
        canonical.seen_count = len({j.canonical_url or j.apply_url for j in grp})
        canonical.alt_urls = [u for u in urls if u != canonical.canonical_url]
        canonical.sources = sources
        out.append(canonical)
    return out


def normalize_and_cluster(raw_jobs: list) -> list:
    from core.normalize import normalize_job  # lazy: avoids an import cycle
    return cluster([normalize_job(r) for r in raw_jobs])


__all__ = ["cluster", "normalize_and_cluster", "content_fingerprint"]
