"""Run checkpointing — durable partial results so a crash/cancel can resume.

Writes to the Phase-2 `run` and `run_source_result` tables and upserts each
source's raw jobs into `job` as they arrive. `done_sources(run_id)` lets a resumed
run skip sources that already completed, re-fetching only what's missing.
"""
from __future__ import annotations

import json
from contextlib import closing
from dataclasses import asdict

from db.connection import connect


def create_run(config, search_id=None) -> int:
    with closing(connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO run (search_id, status, config_json) VALUES (?, 'running', ?)",
            (search_id, json.dumps(asdict(config))),
        )
        return cur.lastrowid


def _source_id(conn, slug: str) -> int | None:
    row = conn.execute("SELECT id FROM source WHERE slug=?", (slug,)).fetchone()
    return row["id"] if row else None


def queue_source(run_id: int, slug: str) -> int:
    with closing(connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO run_source_result (run_id, source_id, status) VALUES (?, ?, 'queued')",
            (run_id, _source_id(conn, slug)),
        )
        return cur.lastrowid


def mark_running(rsr_id: int) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE run_source_result SET status='running' WHERE id=?", (rsr_id,))


def save_source_result(run_id: int, rsr_id: int, result) -> None:
    """Persist the per-source outcome AND upsert its raw jobs (the checkpoint)."""
    # Normalize OUTSIDE the write transaction — it's CPU-bound over up to N jobs
    # and must not hold SQLite's single write lock while other source threads wait.
    from core.normalize import normalize_job
    normalized = [(normalize_job(raw), raw.source) for raw in result.jobs]
    with closing(connect()) as conn, conn:
        conn.execute(
            """UPDATE run_source_result SET status=?, duration_ms=?, jobs_returned=?,
               error_class=?, error_detail=?, http_status=? WHERE id=?""",
            (result.status, result.duration_ms, len(result.jobs),
             result.error_class, result.error_detail, result.http_status, rsr_id),
        )
        for nj, source in normalized:
            sid = _source_id(conn, source)
            conn.execute(
                """
                INSERT INTO job (fingerprint, title, company_name, location_raw,
                                 location_city, location_region, location_country,
                                 work_mode, employment_type, description_text,
                                 salary_min, salary_max, salary_currency,
                                 apply_url, canonical_url, source_id,
                                 first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(fingerprint) DO UPDATE SET
                    last_seen_at=datetime('now'), title=excluded.title,
                    company_name=excluded.company_name, location_raw=excluded.location_raw,
                    description_text=excluded.description_text, apply_url=excluded.apply_url,
                    source_id=excluded.source_id
                """,
                (nj.fingerprint, nj.title, nj.company_name, nj.location_raw,
                 nj.location_city, nj.location_region, nj.location_country,
                 nj.work_mode, nj.employment_type, nj.description_text,
                 nj.salary_min, nj.salary_max, nj.salary_currency,
                 nj.apply_url, nj.canonical_url, sid),
            )


def done_sources(run_id: int) -> set[str]:
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT s.slug FROM run_source_result r JOIN source s ON s.id=r.source_id
               WHERE r.run_id=? AND r.status='done'""",
            (run_id,),
        ).fetchall()
    return {r["slug"] for r in rows}


def finalize_run(run_id: int, summary) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            """UPDATE run SET status=?, finished_at=datetime('now'), jobs_found=?,
               sources_attempted=?, sources_succeeded=?, sources_failed=? WHERE id=?""",
            (summary.status, summary.total_jobs, summary.sources_attempted,
             summary.sources_succeeded, summary.sources_failed, run_id),
        )
