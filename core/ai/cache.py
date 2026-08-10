"""Prompt-response cache keyed on hash(prompt + model + params).

On by default for reranking; TTL configurable via the `ai.cache` setting. Stores
the serialized CompletionResult text + usage so a hit is billed as zero and
labelled `(cached)` in the UI. Expired rows are ignored and lazily purged.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import closing

from core.ai.types import CompletionResult, Message, Usage

_CFG_KEY = "ai.cache"
_DEFAULTS = {"enabled": True, "ttl_hours": 24, "tasks": ["job_rerank", "job_explain"]}


def config() -> dict:
    try:
        from db import get_setting
        cfg = dict(_DEFAULTS)
        cfg.update(get_setting(_CFG_KEY, {}) or {})
        return cfg
    except Exception:
        return dict(_DEFAULTS)


def set_config(**kw) -> None:
    from db import get_setting, set_setting
    cfg = dict(_DEFAULTS)
    cfg.update(get_setting(_CFG_KEY, {}) or {})
    cfg.update(kw)
    set_setting(_CFG_KEY, cfg)


def enabled_for(task: str) -> bool:
    cfg = config()
    return bool(cfg.get("enabled")) and task in (cfg.get("tasks") or [])


def make_key(provider: str, model: str, messages: list[Message], params: dict) -> str:
    payload = json.dumps({
        "provider": provider, "model": model,
        "messages": [(m.role, m.content) for m in messages],
        "params": {k: params[k] for k in sorted(params)},
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get(cache_key: str) -> CompletionResult | None:
    from db.connection import connect
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT response_json, provider, model, task, expires_at "
            "FROM llm_cache WHERE cache_key=?", (cache_key,)
        ).fetchone()
        if row is None:
            return None
        # Expired? drop it and miss.
        exp = conn.execute(
            "SELECT expires_at IS NOT NULL AND expires_at < datetime('now') AS dead "
            "FROM llm_cache WHERE cache_key=?", (cache_key,)
        ).fetchone()
        if exp and exp["dead"]:
            with conn:
                conn.execute("DELETE FROM llm_cache WHERE cache_key=?", (cache_key,))
            return None
    data = json.loads(row["response_json"])
    return CompletionResult(
        text=data["text"],
        usage=Usage(data.get("prompt_tokens", 0), data.get("completion_tokens", 0)),
        model=row["model"], provider=row["provider"], task=row["task"] or "",
        from_cache=True,
    )


def put(cache_key: str, result: CompletionResult, ttl_hours: int) -> None:
    from db.connection import connect
    payload = json.dumps({
        "text": result.text,
        "prompt_tokens": result.usage.prompt_tokens,
        "completion_tokens": result.usage.completion_tokens,
    })
    with closing(connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO llm_cache(cache_key, response_json, provider, model, task, expires_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', ?))
            ON CONFLICT(cache_key) DO UPDATE SET
                response_json = excluded.response_json,
                created_at = datetime('now'),
                expires_at = excluded.expires_at
            """,
            (cache_key, payload, result.provider, result.model, result.task,
             f"+{int(ttl_hours)} hours"),
        )


def purge() -> int:
    """Delete all cached responses. Returns the number removed."""
    from db.connection import connect
    with closing(connect()) as conn, conn:
        n = conn.execute("SELECT count(*) AS n FROM llm_cache").fetchone()["n"]
        conn.execute("DELETE FROM llm_cache")
    return n
