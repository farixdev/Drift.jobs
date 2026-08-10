"""Stage 1 — lexical BM25.

BM25 of each candidate job (title + description) against the resume-derived query
terms (keywords + skills, expanded with synonyms). Cheap; runs on everything.
Computed over the candidate corpus so idf reflects the current result set. Scores
are normalized to 0..1.
"""
from __future__ import annotations

import math
import re

_TOKEN = re.compile(r"[a-z0-9+#.]+")
_K1 = 1.5
_B = 0.75


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if len(t) > 1]


def bm25_scores(docs: list[str], query_terms: list[str]) -> list[float]:
    """Return a 0..1 BM25 score per doc for the query terms."""
    if not docs:
        return []
    query = {t.lower() for t in query_terms if len(t) > 1}
    if not query:
        return [0.0] * len(docs)

    tokenized = [_tokens(d) for d in docs]
    lengths = [len(t) for t in tokenized]
    avg_len = (sum(lengths) / len(lengths)) or 1.0
    n = len(docs)

    # document frequency per query term
    df: dict[str, int] = {}
    for toks in tokenized:
        present = set(toks)
        for q in query:
            if q in present:
                df[q] = df.get(q, 0) + 1

    idf = {q: math.log(1 + (n - df.get(q, 0) + 0.5) / (df.get(q, 0) + 0.5))
           for q in query}

    raw: list[float] = []
    for toks, length in zip(tokenized, lengths):
        counts: dict[str, int] = {}
        for t in toks:
            if t in query:
                counts[t] = counts.get(t, 0) + 1
        score = 0.0
        for q, tf in counts.items():
            denom = tf + _K1 * (1 - _B + _B * length / avg_len)
            score += idf[q] * (tf * (_K1 + 1)) / (denom or 1.0)
        raw.append(score)

    hi = max(raw) or 1.0
    return [r / hi for r in raw]
