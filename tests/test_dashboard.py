"""Phase 10 — dashboard/sources/runs data aggregation."""
from __future__ import annotations

from contextlib import closing

import pytest

import db
from core import dashboard


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    from db import connection
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    db.init_db()
    return p


def _seed(dbpath):
    with closing(db.connection.connect()) as conn, conn:
        conn.execute("INSERT INTO source(slug,display_name,health_status) VALUES "
                     "('greenhouse','GH','healthy'),('themuse','Muse','degraded')")
        conn.execute("INSERT INTO job(fingerprint,title,company_name,source_id,first_seen_at) "
                     "VALUES ('a','Eng','Acme',1,'2026-08-10T00:00')")
        jid = conn.execute("SELECT id FROM job WHERE fingerprint='a'").fetchone()["id"]
        conn.execute("INSERT INTO job_score(job_id,final_score) VALUES (?,85)", (jid,))
        conn.execute("INSERT INTO run(status,jobs_found,sources_succeeded) VALUES ('completed',10,2)")
        rid = conn.execute("SELECT id FROM run LIMIT 1").fetchone()["id"]
        conn.execute("INSERT INTO run_source_result(run_id,source_id,status,duration_ms,jobs_returned) "
                     "VALUES (?,1,'done',1200,10)", (rid,))


class TestDashboard:
    def test_summary_shape(self, dbpath):
        _seed(dbpath)
        s = dashboard.summary()
        assert s["jobs_total"] == 1
        assert s["score_buckets"]["80-100"] == 1
        assert s["last_run"]["status"] == "completed"
        assert "application_metrics" in s and "spend_today" in s

    def test_source_health_aggregates(self, dbpath):
        _seed(dbpath)
        health = {h["slug"]: h for h in dashboard.source_health()}
        assert health["greenhouse"]["health_status"] == "healthy"
        assert health["greenhouse"]["success_rate"] == 100      # 1/1 run done
        assert health["greenhouse"]["avg_ms"] == 1200
        assert health["themuse"]["health_status"] == "degraded"

    def test_recent_jobs_and_runs(self, dbpath):
        _seed(dbpath)
        jobs = dashboard.recent_jobs()
        assert jobs and jobs[0]["title"] == "Eng" and jobs[0]["score"] == 85
        runs = dashboard.recent_runs()
        assert runs and runs[0]["jobs_found"] == 10

    def test_empty_db_does_not_crash(self, dbpath):
        s = dashboard.summary()
        assert s["jobs_total"] == 0 and s["last_run"] is None
