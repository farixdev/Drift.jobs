"""Migration 003 — AI layer support tables: prompt-response cache + usage log.

- `llm_cache` backs the prompt-response cache keyed on hash(prompt+model+params),
  with a TTL, so repeated reranks don't re-bill.
- `llm_usage` is the append-only ledger the cost meter aggregates per task / run /
  day / provider.

Both are additive; `down()` drops them cleanly.
"""
from __future__ import annotations

import sqlite3

VERSION = 3
NAME = "ai_cache_usage"

_UP = [
    """
    CREATE TABLE llm_cache (
        cache_key TEXT PRIMARY KEY,
        response_json TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        task TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT
    )
    """,
    "CREATE INDEX idx_llm_cache_expires ON llm_cache(expires_at)",
    """
    CREATE TABLE llm_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now')),
        run_id INTEGER REFERENCES run(id) ON DELETE SET NULL,
        task TEXT NOT NULL DEFAULT '',
        provider TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL NOT NULL DEFAULT 0,
        from_cache INTEGER NOT NULL DEFAULT 0,
        ok INTEGER NOT NULL DEFAULT 1,
        error_class TEXT NOT NULL DEFAULT '',
        fallback_depth INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX idx_llm_usage_ts ON llm_usage(ts)",
    "CREATE INDEX idx_llm_usage_provider ON llm_usage(provider)",
]

_DOWN = [
    "DROP TABLE IF EXISTS llm_usage",
    "DROP TABLE IF EXISTS llm_cache",
]


def up(conn: sqlite3.Connection) -> None:
    for stmt in _UP:
        conn.execute(stmt)


def down(conn: sqlite3.Connection) -> None:
    for stmt in _DOWN:
        conn.execute(stmt)
