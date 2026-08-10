"""Drift data layer — public API.

The schema is the Phase 2 target (14 tables + FTS5, see db/migrations/). The
functions below preserve the exact call surface the 1.x UI depends on
(`ui/worker.py`, `ui/screen_results.py`) but are reimplemented on the new
`job` / `application` / `cover_letter` tables. This keeps the app running and
testable across the rewrite (Prime Directive 5) while the storage moves out from
under it.

Legacy identity: the old string `job_id` is a URL fingerprint. It is stored as
`job.fingerprint`; the shims translate fingerprint <-> integer `job.id`.
Status model: a job with no `application` row is implicitly 'new'; acting on a
job creates/updates its application; un-saving (setting 'new') removes it.
"""
from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from db import connection
from db.connection import connect
from db.migrations import LATEST_VERSION, current_version, migrate
from models import STATUS_DISMISSED, STATUS_NEW, Job

# Re-exported so callers can still do `from db import DB_PATH` if needed.
DB_PATH = connection.DB_PATH


# --------------------------------------------------------------------------- #
# Initialisation
# --------------------------------------------------------------------------- #
def _needs_backup(path: Path) -> bool:
    """True when an existing, non-fresh database has pending migrations — so we
    file-copy it before any potentially destructive migration (m002 import,
    m005 fingerprint merge, …) runs. A fresh/absent DB needs no backup."""
    if not path.is_file():
        return False
    try:
        from db.migrations import LATEST_VERSION
        with closing(sqlite3.connect(str(path))) as probe:
            has_data = probe.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name IN ('jobs','job')"
            ).fetchone()
            row = probe.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_migration'"
            ).fetchone()
            applied = 0
            if row is not None:
                r = probe.execute("SELECT MAX(version) v FROM _migration").fetchone()
                applied = (r["v"] if r and r["v"] is not None else 0) if False else (r[0] or 0)
        return bool(has_data) and applied < LATEST_VERSION
    except sqlite3.Error:
        return False


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = path.with_suffix(f".db.bak.pre-migration-{stamp}")
    shutil.copy2(path, dest)
    return dest


def init_db() -> None:
    """Bring the database up to the latest schema. Idempotent; safe to call on
    every scan. Backs up a non-fresh database before applying pending migrations."""
    path = connection.DB_PATH
    if _needs_backup(path):
        _backup(path)
    with closing(connect()) as conn:
        migrate(conn)


def schema_version() -> int:
    with closing(connect()) as conn:
        return current_version(conn)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _source_id(conn: sqlite3.Connection, slug: str) -> int | None:
    """Resolve a source slug to its id, creating a minimal row on first sight so
    `job.source_id` always has a valid target. Phase 6 enriches these rows."""
    slug = (slug or "").strip()
    if not slug:
        return None
    conn.execute(
        "INSERT OR IGNORE INTO source(slug, display_name) VALUES (?, ?)",
        (slug, slug.title()),
    )
    row = conn.execute("SELECT id FROM source WHERE slug=?", (slug,)).fetchone()
    return row["id"] if row else None


def _job_id_for(conn: sqlite3.Connection, fingerprint: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM job WHERE fingerprint=?", (fingerprint,)
    ).fetchone()
    return row["id"] if row else None


def _ensure_job(conn: sqlite3.Connection, fingerprint: str) -> int:
    """Return job.id for a fingerprint, creating a minimal legacy-flagged row if
    the job was never recorded (mirrors 1.x set_status on an unknown job)."""
    jid = _job_id_for(conn, fingerprint)
    if jid is not None:
        return jid
    conn.execute(
        "INSERT OR IGNORE INTO job(fingerprint, legacy) VALUES (?, 1)",
        (fingerprint,),
    )
    return _job_id_for(conn, fingerprint)  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Per-scan dedupe (pure — unchanged from 1.x)
# --------------------------------------------------------------------------- #
def dedupe_by_url(jobs: list) -> list:
    """Remove duplicate URLs within one scan — does not block rescans."""
    seen: set[str] = set()
    fresh: list = []
    for job in jobs:
        key = (getattr(job, "url", "") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        fresh.append(job)
    return fresh


# --------------------------------------------------------------------------- #
# Cross-scan state (reimplemented on job/application)
# --------------------------------------------------------------------------- #
def known_ids() -> set[str]:
    with closing(connect()) as conn:
        rows = conn.execute("SELECT fingerprint FROM job").fetchall()
    return {r["fingerprint"] for r in rows}


def statuses_for(ids: list[str]) -> dict[str, str]:
    """Map each fingerprint to its status. A job with no application row reads as
    'new' (the 1.x default). Only fingerprints present in `job` are returned."""
    if not ids:
        return {}
    out: dict[str, str] = {}
    with closing(connect()) as conn:
        for i in range(0, len(ids), 400):
            chunk = ids[i : i + 400]
            placeholders = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"""
                SELECT j.fingerprint AS fp, COALESCE(a.status, 'new') AS status
                  FROM job j
                  LEFT JOIN application a ON a.job_id = j.id
                 WHERE j.fingerprint IN ({placeholders})
                """,
                chunk,
            ).fetchall()
            out.update({r["fp"]: r["status"] for r in rows})
    return out


def dismissed_ids() -> set[str]:
    with closing(connect()) as conn:
        rows = conn.execute(
            """
            SELECT j.fingerprint AS fp
              FROM job j JOIN application a ON a.job_id = j.id
             WHERE a.status = ?
            """,
            (STATUS_DISMISSED,),
        ).fetchall()
    return {r["fp"] for r in rows}


def record_seen(jobs: list[Job]) -> None:
    """Upsert scanned jobs: preserve first_seen_at + status, refresh last_seen_at
    and the re-scrapeable fields. Never creates or alters an application row."""
    if not jobs:
        return
    with closing(connect()) as conn, conn:
        for job in jobs:
            sid = _source_id(conn, job.source)
            conn.execute(
                """
                INSERT INTO job
                    (fingerprint, title, company_name, location_raw,
                     description_text, work_mode, employment_type,
                     apply_url, canonical_url, source_id,
                     first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(fingerprint) DO UPDATE SET
                    last_seen_at    = datetime('now'),
                    title           = excluded.title,
                    company_name    = excluded.company_name,
                    location_raw    = excluded.location_raw,
                    description_text= excluded.description_text,
                    apply_url       = excluded.apply_url,
                    canonical_url   = excluded.canonical_url,
                    source_id       = excluded.source_id
                """,
                (
                    job.job_id, job.title, job.company, job.location,
                    (job.description or "")[:8000],
                    "remote" if job.remote else "unspecified",
                    job.job_type or "",
                    job.url, job.url, sid,
                ),
            )


def set_status(job_id: str, status: str) -> None:
    """Set a job's application status. Setting the 1.x 'new' state removes the
    application row entirely (i.e. un-save)."""
    with closing(connect()) as conn, conn:
        jid = _ensure_job(conn, job_id)
        if status == STATUS_NEW:
            conn.execute("DELETE FROM application WHERE job_id = ?", (jid,))
            return
        applied_at = datetime.now().isoformat(timespec="seconds") if status == "applied" else None
        conn.execute(
            """
            INSERT INTO application (job_id, status, applied_at)
            VALUES (?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status = excluded.status,
                applied_at = COALESCE(application.applied_at, excluded.applied_at),
                updated_at = datetime('now')
            """,
            (jid, status, applied_at),
        )


def save_cover_letter(job_id: str, text: str) -> None:
    """Persist a cover letter for a job and link it to the job's application
    (creating a minimal 'saved' application if none exists yet)."""
    with closing(connect()) as conn, conn:
        jid = _ensure_job(conn, job_id)
        cur = conn.execute(
            "INSERT INTO cover_letter(job_id, body) VALUES (?, ?)", (jid, text)
        )
        cover_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO application (job_id, status, cover_letter_id)
            VALUES (?, 'saved', ?)
            ON CONFLICT(job_id) DO UPDATE SET
                cover_letter_id = excluded.cover_letter_id,
                updated_at = datetime('now')
            """,
            (jid, cover_id),
        )


def get_cover_letter(job_id: str) -> str:
    with closing(connect()) as conn:
        row = conn.execute(
            """
            SELECT c.body AS body
              FROM cover_letter c JOIN job j ON j.id = c.job_id
             WHERE j.fingerprint = ?
             ORDER BY c.id DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    return (row["body"] if row else "") or ""


def mark_jobs_seen(jobs: list) -> None:
    """Back-compat shim for 1.x callers."""
    record_seen([j for j in jobs if isinstance(j, Job)])


# --------------------------------------------------------------------------- #
# Generic settings store (the `setting` table) — used by the AI layer and later
# phases for JSON-valued config (routing, pricing, cache TTL, feature flags).
# --------------------------------------------------------------------------- #
def get_setting(key: str, default=None):
    import json as _json
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT value_json FROM setting WHERE key=?", (key,)
        ).fetchone()
    if row is None:
        return default
    try:
        return _json.loads(row["value_json"])
    except (ValueError, TypeError):
        return default


def set_setting(key: str, value) -> None:
    import json as _json
    payload = _json.dumps(value)
    with closing(connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO setting(key, value_json, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = datetime('now')
            """,
            (key, payload),
        )
