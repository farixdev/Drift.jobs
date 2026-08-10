"""Phase 8b — three-stage ranking tests.

Lexical BM25 and blend logic are pure. The semantic stage is exercised through
its graceful-degradation path (no embedder → None). The orchestrator is tested
with the LLM stage off (deterministic) and asserts explainable sub-scores.
"""
from __future__ import annotations

import pytest

import db
from core.ranking import rank_jobs
from core.ranking.blend import freshness_factor, is_blocked, weights
from core.ranking.lexical import bm25_scores
from core.normalize import normalize_job
from core.scraper.base import RawJob


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    from db import connection
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    db.init_db()
    return p


# --------------------------------------------------------------------------- #
class TestBM25:
    def test_ranks_relevant_higher(self):
        docs = [
            "Senior Python engineer building Django REST APIs and Postgres",
            "Registered nurse providing ICU patient care in the ward",
            "Python data engineer with Airflow, Spark and Postgres",
        ]
        scores = bm25_scores(docs, ["python", "postgres", "django"])
        assert scores[0] > scores[1]          # python role beats nurse
        assert scores[2] > scores[1]
        assert max(scores) == pytest.approx(1.0)

    def test_no_query_is_zero(self):
        assert bm25_scores(["anything here"], []) == [0.0]

    def test_empty_docs(self):
        assert bm25_scores([], ["python"]) == []


class TestBlend:
    def test_freshness_decay(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        fresh = freshness_factor(now.isoformat())
        old = freshness_factor((now - timedelta(days=60)).isoformat())
        assert fresh > old
        assert freshness_factor(None) == 0.9          # unknown -> mild neutral
        assert old >= 0.4                              # floored

    def test_weights_default(self):
        w = weights()
        assert set(w) >= {"lexical", "semantic", "llm"}

    def test_blocklist_company(self):
        job = _job("Engineer", "Acme Inc")
        assert is_blocked(job, {"company": {"acme"}}) is True
        assert is_blocked(job, {"company": {"globex"}}) is False


def _job(title, company, desc="python django", **kw):
    from models import Job
    return Job(title=title, company=company, location="Remote", job_type="",
               url="https://x.com/1", source="greenhouse", description=desc, **kw)


class TestRankJobs:
    def _norm(self, title, company, desc, source="greenhouse", posted=None):
        return normalize_job(RawJob(title=title, company=company, location="Remote",
                                    description=desc, url=f"https://{source}.com/{title}",
                                    source=source, remote=True, posted=posted or ""))

    def test_explainable_scores_without_llm(self, dbpath):
        normalized = [
            self._norm("Senior Python Engineer", "Acme",
                       "Python Django Postgres backend REST APIs " * 10),
            self._norm("Marketing Manager", "Globex",
                       "Brand strategy and social campaigns " * 10),
        ]
        jobs = rank_jobs(normalized, "Python Django Postgres engineer",
                         skills=["Python", "Django", "Postgres"],
                         keywords=["python developer"], use_llm=False)
        assert len(jobs) == 2
        # sorted by score desc; the python role wins
        assert jobs[0].title == "Senior Python Engineer"
        # every job is explainable: lexical + freshness sub-scores present
        for j in jobs:
            assert "lexical" in j.subscores and "freshness" in j.subscores
            assert "semantic" not in j.subscores   # no embedder in tests
            assert 0 <= j.score <= 100

    def test_blocklist_filters_out(self, dbpath):
        from contextlib import closing
        from db.connection import connect
        with closing(connect()) as conn, conn:
            conn.execute("INSERT INTO blocklist(type, value) VALUES ('company', 'Globex')")
        normalized = [
            self._norm("Python Engineer", "Acme", "Python Django " * 10),
            self._norm("Python Engineer", "Globex", "Python Django " * 10),
        ]
        jobs = rank_jobs(normalized, "python", skills=["Python"],
                         keywords=["python"], use_llm=False)
        assert [j.company for j in jobs] == ["Acme"]   # Globex blocked

    def test_empty(self, dbpath):
        assert rank_jobs([], "resume", use_llm=False) == []
