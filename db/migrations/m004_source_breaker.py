"""Migration 004 — circuit-breaker state on the source table.

Adds `disabled_until`: when a source trips its breaker (5 consecutive failures),
it's disabled until this timestamp, after which a half-open probe is allowed.
Additive; down() is a no-op because SQLite can't drop a column without a table
rebuild and the column is harmless if left.
"""
from __future__ import annotations

import sqlite3

VERSION = 4
NAME = "source_breaker"


def up(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(source)").fetchall()}
    if "disabled_until" not in cols:
        conn.execute("ALTER TABLE source ADD COLUMN disabled_until TEXT")


def down(conn: sqlite3.Connection) -> None:
    # SQLite pre-3.35 can't DROP COLUMN; the column is inert, so leave it.
    pass
