"""Dashboard + Sources + Runs data aggregation (Phase 10).

Read-only queries that back the dashboard home, the sources health page, and the
runs history — kept out of the UI so they're testable.
"""
from __future__ import annotations

from contextlib import closing

from db.connection import connect


def summary() -> dict:
    from core import tracker
    from core.ai import cost
    with closing(connect()) as conn:
        jobs_total = conn.execute("SELECT count(*) n FROM job WHERE is_active=1").fetchone()["n"]
        # score distribution buckets from the latest job_score per job (if any)
        buckets = {"0-39": 0, "40-59": 0, "60-79": 0, "80-100": 0}
        for r in conn.execute(
                "SELECT final_score FROM job_score WHERE final_score IS NOT NULL").fetchall():
            s = r["final_score"] or 0
            key = "80-100" if s >= 80 else "60-79" if s >= 60 else "40-59" if s >= 40 else "0-39"
            buckets[key] += 1
        last_run = conn.execute(
            "SELECT started_at, finished_at, status, jobs_found FROM run "
            "ORDER BY started_at DESC LIMIT 1").fetchone()
        active_searches = conn.execute(
            "SELECT count(*) n FROM search WHERE is_active=1").fetchone()["n"]
    return {
        "jobs_total": jobs_total,
        "score_buckets": buckets,
        "last_run": dict(last_run) if last_run else None,
        "active_searches": active_searches,
        "application_metrics": tracker.metrics(),
        "upcoming": tracker.upcoming_actions(6),
        "source_health": source_health(),
        "spend_today": cost.spend_summary("day"),
        "spend_month": cost.spend_summary("month"),
    }


def recent_jobs(limit: int = 8) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT j.title, j.company_name, j.location_raw, j.work_mode,
                      s.slug AS source, j.first_seen_at,
                      (SELECT final_score FROM job_score sc WHERE sc.job_id=j.id
                       ORDER BY scored_at DESC LIMIT 1) AS score
                 FROM job j LEFT JOIN source s ON s.id=j.source_id
                WHERE j.is_active=1 ORDER BY j.first_seen_at DESC, j.id DESC LIMIT ?""",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def source_health() -> list[dict]:
    """Per-source health + aggregates over recent run_source_result rows."""
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT s.slug, s.display_name, s.category, s.adapter_type,
                      s.health_status, s.last_success_at, s.last_error,
                      s.consecutive_failures, s.is_enabled,
                      (SELECT count(*) FROM run_source_result r WHERE r.source_id=s.id) AS runs,
                      (SELECT count(*) FROM run_source_result r WHERE r.source_id=s.id
                        AND r.status='done') AS ok_runs,
                      (SELECT avg(r.duration_ms) FROM run_source_result r WHERE r.source_id=s.id) AS avg_ms,
                      (SELECT avg(r.jobs_returned) FROM run_source_result r WHERE r.source_id=s.id
                        AND r.status='done') AS avg_jobs
                 FROM source s ORDER BY s.category, s.slug""").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["success_rate"] = round(100 * d["ok_runs"] / d["runs"]) if d["runs"] else None
        d["avg_ms"] = round(d["avg_ms"]) if d["avg_ms"] is not None else None
        d["avg_jobs"] = round(d["avg_jobs"], 1) if d["avg_jobs"] is not None else None
        out.append(d)
    return out


def recent_runs(limit: int = 25) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT r.id, r.started_at, r.finished_at, r.status, r.jobs_found,
                      r.sources_succeeded, r.sources_failed,
                      (SELECT count(*) FROM run_source_result rr WHERE rr.run_id=r.id) AS sources
                 FROM run r ORDER BY r.started_at DESC LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]
