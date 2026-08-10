"""Versioned migration runner.

Migrations are ordinary Python modules exposing `VERSION`, `NAME`, `up(conn)`,
and `down(conn)`. They apply in ascending VERSION order, each inside its own
transaction, and each is recorded in the `_migration` bookkeeping table so
re-running is a no-op. `PRAGMA user_version` is mirrored for quick inspection.

To add a migration: create `mNNN_name.py` and append it to `ALL_MIGRATIONS`.
"""
from __future__ import annotations

import sqlite3

from db.migrations import (
    m001_initial_schema,
    m002_import_legacy,
    m003_ai_cache_usage,
    m004_source_breaker,
    m005_content_fingerprint,
    m006_job_embedding,
)

# Ordered by VERSION. New migrations go on the end.
ALL_MIGRATIONS = [m001_initial_schema, m002_import_legacy, m003_ai_cache_usage,
                  m004_source_breaker, m005_content_fingerprint, m006_job_embedding]

LATEST_VERSION = max(m.VERSION for m in ALL_MIGRATIONS)


def _ensure_bookkeeping(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migration (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_bookkeeping(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM _migration").fetchone()
    return row["v"] or 0


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply every pending migration in order. Returns the versions applied.

    Each migration runs atomically: a failure rolls its transaction back and
    re-raises, leaving the DB at the last good version rather than half-applied.
    """
    _ensure_bookkeeping(conn)
    applied: list[int] = []
    have = current_version(conn)
    for migration in sorted(ALL_MIGRATIONS, key=lambda m: m.VERSION):
        if migration.VERSION <= have:
            continue
        try:
            conn.execute("BEGIN")
            migration.up(conn)
            conn.execute(
                "INSERT INTO _migration(version, name) VALUES (?, ?)",
                (migration.VERSION, migration.NAME),
            )
            conn.execute(f"PRAGMA user_version = {migration.VERSION}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append(migration.VERSION)
    return applied


def rollback_to(conn: sqlite3.Connection, target_version: int) -> list[int]:
    """Roll back down() migrations until only `target_version` remains applied.

    Used by tests and by the reversibility guarantee; the app never calls this
    at runtime. Paired with the pre-migration file backup for real recovery.
    """
    _ensure_bookkeeping(conn)
    reverted: list[int] = []
    by_version = {m.VERSION: m for m in ALL_MIGRATIONS}
    have = current_version(conn)
    for version in sorted(by_version, reverse=True):
        if version <= target_version or version > have:
            continue
        migration = by_version[version]
        try:
            conn.execute("BEGIN")
            migration.down(conn)
            conn.execute("DELETE FROM _migration WHERE version = ?", (version,))
            conn.execute(f"PRAGMA user_version = {max(target_version, 0)}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        reverted.append(version)
    return reverted
