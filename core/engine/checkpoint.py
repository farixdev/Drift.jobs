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
    with closing(connect()) as conn, conn:
        conn.execute(
            """UPDATE run_source_result SET status=?, duration_ms=?, jobs_returned=?,
               error_class=?, error_detail=?, http_status=? WHERE id=?""",
            (result.status, result.duration_ms, len(result.jobs),
             result.error_class, result.error_detail, result.http_status, rsr_id),
        )
        for raw in result.jobs:
            sid = _source_id(conn, raw.source)
            conn.execute(
                """
                INSERT INTO job (fingerprint, title, company_name, location_raw,
                                 description_text, work_mode, employment_type,
                                 salary_currency, apply_url, canonical_url, source_id,
                                 first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(fingerprint) DO UPDATE SET
                    last_seen_at=datetime('now'), title=excluded.title,
                    company_name=excluded.company_name, location_raw=excluded.location_raw,
                    description_text=excluded.description_text, apply_url=excluded.apply_url,
                    source_id=excluded.source_id
                """,
                (raw.id, raw.title, raw.company, raw.location, (raw.description or "")[:8000],
                 "remote" if raw.remote else "unspecified", raw.job_type or "",
                 raw.url, raw.url, sid),
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
