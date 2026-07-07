import sqlite3
from pathlib import Path

from models import STATUS_DISMISSED, STATUS_NEW, Job, job_fingerprint

DB_PATH = Path(__file__).resolve().parent / "jobs.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                url TEXT,
                title TEXT,
                company TEXT,
                location TEXT,
                source TEXT,
                score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'new',
                cover_letter TEXT DEFAULT '',
                first_seen TEXT,
                last_seen TEXT
            )
            """
        )
        # Legacy table from 1.x — harmless to keep.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_jobs (
                url TEXT PRIMARY KEY, title TEXT, company TEXT,
                source TEXT, scraped_at TEXT
            )
            """
        )


# --- Per-scan dedupe (unchanged public API) --------------------------------

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


# --- Cross-scan state -------------------------------------------------------

def known_ids() -> set[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT job_id FROM jobs").fetchall()
    return {r["job_id"] for r in rows}


def statuses_for(ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    out: dict[str, str] = {}
    with _connect() as conn:
        for i in range(0, len(ids), 400):
            chunk = ids[i : i + 400]
            q = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT job_id, status FROM jobs WHERE job_id IN ({q})", chunk
            ).fetchall()
            out.update({r["job_id"]: r["status"] for r in rows})
    return out


def dismissed_ids() -> set[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT job_id FROM jobs WHERE status = ?", (STATUS_DISMISSED,)
        ).fetchall()
    return {r["job_id"] for r in rows}


def record_seen(jobs: list[Job]) -> None:
    """Upsert jobs from a scan: preserve status/first_seen, refresh last_seen."""
    if not jobs:
        return
    with _connect() as conn:
        for job in jobs:
            conn.execute(
                """
                INSERT INTO jobs (job_id, url, title, company, location, source,
                                  score, status, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(job_id) DO UPDATE SET
                    last_seen = datetime('now'),
                    score = excluded.score,
                    location = excluded.location
                """,
                (
                    job.job_id, job.url, job.title, job.company, job.location,
                    job.source, int(job.score), STATUS_NEW,
                ),
            )


def set_status(job_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, status, first_seen, last_seen)
            VALUES (?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET status = excluded.status
            """,
            (job_id, status),
        )


def save_cover_letter(job_id: str, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, cover_letter, first_seen, last_seen)
            VALUES (?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET cover_letter = excluded.cover_letter
            """,
            (job_id, text),
        )


def get_cover_letter(job_id: str) -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT cover_letter FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    return (row["cover_letter"] if row else "") or ""


def mark_jobs_seen(jobs: list) -> None:
    """Back-compat shim for 1.x callers."""
    record_seen([j for j in jobs if isinstance(j, Job)])
