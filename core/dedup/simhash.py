"""64-bit SimHash for near-duplicate description detection.

Two postings of the same role have near-identical descriptions → small Hamming
distance between their simhashes, even when a board reformats the text. Used by
the clusterer to merge title/formatting variants that share a company + location.
"""
from __future__ import annotations

import hashlib
import re

_TOKEN = re.compile(r"[a-z0-9]+")
_BITS = 64


def _hash_token(token: str) -> int:
    return int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:8], "big")


def simhash(text: str, limit: int = 2000) -> int:
    tokens = _TOKEN.findall((text or "")[:limit].lower())
    if not tokens:
        return 0
    # Weight by term frequency (shingling could be added; TF is enough here).
    weights: dict[str, int] = {}
    for t in tokens:
        if len(t) > 1:
            weights[t] = weights.get(t, 0) + 1
    vector = [0] * _BITS
    for token, w in weights.items():
        h = _hash_token(token)
        for i in range(_BITS):
            vector[i] += w if (h >> i) & 1 else -w
    out = 0
    for i in range(_BITS):
        if vector[i] > 0:
            out |= (1 << i)
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def near(a: int, b: int, threshold: int = 3) -> bool:
    if a == 0 or b == 0:
        return False
    return hamming(a, b) <= threshold
