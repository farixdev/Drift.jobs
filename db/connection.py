"""SQLite connection management for Drift.

Single source of truth for the DB path and the per-connection pragmas the whole
app relies on: WAL journaling, enforced foreign keys, and a busy timeout so the
many short-lived connections the UI opens don't trip over each other.

Tests override `DB_PATH` (monkeypatch this module attribute) to run against a
throwaway file — every helper reads the attribute at call time, never caches it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# Same on-disk location the app has always used. Kept stable so an existing
# install's history is found and migrated in place (see migrations/m002).
DB_PATH = Path(__file__).resolve().parent / "jobs.db"

# Generous busy timeout: under a wide concurrent scan many source threads write
# health/checkpoint rows; SQLite serialises writers, so each must wait for the
# lock rather than error out.
_BUSY_TIMEOUT_MS = 30000


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with Drift's standard pragmas applied.

    WAL mode is a property of the database file and persists once set; foreign
    keys and busy_timeout are per-connection and must be set every time.
    """
    target = Path(path) if path is not None else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    # foreign_keys must be set OUTSIDE any transaction — do it first, always.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def fts5_available(conn: sqlite3.Connection) -> bool:
    """True when this sqlite build has FTS5 compiled in. Phase 2 requires it."""
    try:
        conn.execute("CREATE VIRTUAL TABLE temp._fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE temp._fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False
