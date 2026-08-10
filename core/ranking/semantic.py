"""Stage 2 — semantic similarity.

Embeds the resume and each job description via the AI layer's `embeddings` task,
caches per (fingerprint, model), and scores cosine similarity → 0..1. Requires an
embedding-capable provider (Ollama local, or an OpenAI/Gemini/Mistral key); when
none is configured this stage degrades gracefully — `available()` is False and the
blender drops semantic weight rather than faking a number.
"""
from __future__ import annotations

import json
import math
from contextlib import closing


def available() -> bool:
    """True when the embeddings task route has a usable provider."""
    try:
        from core.ai import routing
        from core.ai.keystore import default_store
        from core.ai.registry import PROVIDERS
        store = default_store()
        for provider_slug, _model in routing.get_route("embeddings").chain():
            spec = PROVIDERS.get(provider_slug)
            if spec and (not spec.needs_key or store.has_key(provider_slug)):
                # Ollama must actually be reachable; treat keyed providers as ready.
                if provider_slug == "ollama":
                    return _ollama_up()
                return True
    except Exception:
        return False
    return False


def _ollama_up() -> bool:
    try:
        import requests
        requests.get("http://localhost:11434/api/tags", timeout=1.5)
        return True
    except Exception:
        return False


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, dot / (na * nb))


def _cache_get(fingerprint: str, model: str):
    from db.connection import connect
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT vector_json FROM job_embedding WHERE fingerprint=? AND model=?",
            (fingerprint, model)).fetchone()
    return json.loads(row["vector_json"]) if row else None


def _cache_put(fingerprint: str, model: str, vec: list[float]):
    from db.connection import connect
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO job_embedding(fingerprint, model, vector_json) VALUES (?,?,?)",
            (fingerprint, model, json.dumps(vec)))


def semantic_scores(resume_text: str, jobs: list) -> list[float] | None:
    """Return a 0..1 cosine score per job, or None if embeddings are unavailable.

    `jobs` items must expose `.fingerprint` and `.description_text`.
    """
    if not available() or not jobs:
        return None
    try:
        from core.ai import LLMManager, routing
        mgr = LLMManager()
        model = routing.get_route("embeddings").model

        resume_vec = mgr.embed_task("embeddings", [resume_text[:4000]]).vectors[0]

        # Reuse cached embeddings; embed only the misses, in one batched call.
        vectors: list[list[float] | None] = []
        to_embed, idx = [], []
        for i, j in enumerate(jobs):
            cached = _cache_get(j.fingerprint, model)
            vectors.append(cached)
            if cached is None:
                to_embed.append((j.description_text or j.title or "")[:4000])
                idx.append(i)
        if to_embed:
            fresh = mgr.embed_task("embeddings", to_embed).vectors
            for pos, vec in zip(idx, fresh):
                vectors[pos] = vec
                _cache_put(jobs[pos].fingerprint, model, vec)

        return [_cosine(resume_vec, v or []) for v in vectors]
    except Exception:
        return None  # any embedding failure -> degrade, don't fake
