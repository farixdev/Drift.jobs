"""Migration 002 — import 1.x user history, then retire the legacy tables.

The only irreplaceable data in a 1.x install is the user's save/apply/dismiss
state and any saved cover letters (audit §9.4a). Everything else is re-scrapeable.
This migration copies that state from the legacy `jobs` table into the new
`job` + `application` + `cover_letter` tables, keyed by the old `job_id` (which
was a URL fingerprint), then drops `jobs` and the dead `seen_jobs` table.

Safety: `db/__init__.init_db()` file-copies the database to a `.bak.pre-phase2`
backup BEFORE any migration runs on a legacy DB, so this is recoverable even
though it drops tables. `down()` additionally reconstructs the legacy `jobs`
table from the new schema on a best-effort basis.

On a fresh install there is no `jobs` table, so `up()` is a no-op.
"""
from __future__ import annotations

import sqlite3

VERSION = 2
NAME = "import_legacy"

# 1.x statuses. 'new' means "seen but not acted on" -> no application row.
_ACTIONED = {"saved", "applied", "dismissed"}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _source_id(conn: sqlite3.Connection, slug: str) -> int | None:
    slug = (slug or "").strip()
    if not slug:
        return None
    conn.execute(
        "INSERT OR IGNORE INTO source(slug, display_name) VALUES (?, ?)",
        (slug, slug.title()),
    )
    row = conn.execute("SELECT id FROM source WHERE slug=?", (slug,)).fetchone()
    return row["id"] if row else None


def up(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "jobs"):
        return  # fresh install — nothing to import

    rows = conn.execute(
        """
        SELECT job_id, url, title, company, location, source, score,
               status, cover_letter, first_seen, last_seen
          FROM jobs
        """
    ).fetchall()

    for r in rows:
        fingerprint = r["job_id"]
        if not fingerprint:
            continue  # unusable without an identity

        title = r["title"] or ""
        # A row with no title is a 1.x orphan (set_status/save_cover_letter on a
        # job that was never fully recorded). Keep it — it carries user intent —
        # but flag it so later phases can tell it apart from a full listing.
        is_legacy_partial = 1 if not title else 0
        sid = _source_id(conn, r["source"])

        conn.execute(
            """
            INSERT OR IGNORE INTO job
                (fingerprint, title, company_name, location_raw,
                 apply_url, canonical_url, source_id,
                 first_seen_at, last_seen_at, legacy)
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    COALESCE(?, datetime('now')), COALESCE(?, datetime('now')), ?)
            """,
            (
                fingerprint, title, r["company"] or "", r["location"] or "",
                r["url"] or "", r["url"] or "", sid,
                r["first_seen"], r["last_seen"], is_legacy_partial,
            ),
        )
        job_row = conn.execute(
            "SELECT id FROM job WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if job_row is None:
            continue
        job_id = job_row["id"]

        cover_letter_id = None
        if (r["cover_letter"] or "").strip():
            cur = conn.execute(
                "INSERT INTO cover_letter(job_id, body) VALUES (?, ?)",
                (job_id, r["cover_letter"]),
            )
            cover_letter_id = cur.lastrowid

        status = (r["status"] or "new").strip().lower()
        if status in _ACTIONED:
            applied_at = r["last_seen"] if status == "applied" else None
            conn.execute(
                """
                INSERT OR IGNORE INTO application
                    (job_id, status, applied_at, cover_letter_id)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, status, applied_at, cover_letter_id),
            )
        elif cover_letter_id is not None:
            # A saved letter but status 'new': create a minimal application so the
            # letter stays linked to something actionable.
            conn.execute(
                """
                INSERT OR IGNORE INTO application (job_id, status, cover_letter_id)
                VALUES (?, 'saved', ?)
                """,
                (job_id, cover_letter_id),
            )

    conn.execute("DROP TABLE IF EXISTS jobs")
    conn.execute("DROP TABLE IF EXISTS seen_jobs")


def down(conn: sqlite3.Connection) -> None:
    """Best-effort reconstruction of the legacy `jobs` table from the new schema.

    Paired with the pre-migration file backup, this makes the drop recoverable.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY, url TEXT, title TEXT, company TEXT,
            location TEXT, source TEXT, score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new', cover_letter TEXT DEFAULT '',
            first_seen TEXT, last_seen TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_jobs (
            url TEXT PRIMARY KEY, title TEXT, company TEXT,
            source TEXT, scraped_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO jobs
            (job_id, url, title, company, location, source, score, status,
             cover_letter, first_seen, last_seen)
        SELECT j.fingerprint, j.apply_url, j.title, j.company_name, j.location_raw,
               COALESCE(s.slug, ''), 0,
               COALESCE(a.status, 'new'),
               COALESCE((SELECT body FROM cover_letter c WHERE c.job_id = j.id
                         ORDER BY c.id DESC LIMIT 1), ''),
               j.first_seen_at, j.last_seen_at
          FROM job j
          LEFT JOIN source s ON s.id = j.source_id
          LEFT JOIN application a ON a.job_id = j.id
        """
    )
