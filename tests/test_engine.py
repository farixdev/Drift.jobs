"""Phase 7 — execution engine tests.

`run_source` is mocked so these are deterministic and offline. Covers config
clamping, the token bucket, cancellation, priority order, streaming, checkpoint +
resume, graceful widening, and cancel/timeout status.
"""
from __future__ import annotations

from contextlib import closing

import pytest

import db
from core.engine import CancelToken, RunConfig, events
from core.engine.engine import ScanEngine, _dedupe, _widen
from core.engine.ratelimit import TokenBucket
from core.sources import SearchCriteria
from core.sources.spec import RawJob, SourceDefinition, SourceResult


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    from db import connection
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    db.init_db()
    return p


def _defn(slug, adapter_type="api"):
    return SourceDefinition(
        slug=slug, display_name=slug.title(), category="ats", adapter_type=adapter_type,
        base_url=f"https://{slug}.example.com/api", auth_type="none", auth_env_key="",
        rate_limit_rpm=120, concurrency_limit=4, robots_check=False,
        query_mapper=lambda c: [], response_parser=lambda r, s: [])


def _raw(slug, i):
    return RawJob(title=f"Engineer {i}", company=slug.title(), location="Remote",
                  description="python", url=f"https://{slug}.example.com/j/{i}", source=slug)


def _result(slug, n, status="done"):
    return SourceResult(slug=slug, status=status,
                        jobs=[_raw(slug, i) for i in range(n)],
                        duration_ms=10, boards_attempted=1, boards_succeeded=1,
                        finished_at="2026-08-10T00:00:00+00:00")


# --------------------------------------------------------------------------- #
class TestConfig:
    def test_clamping(self):
        c = RunConfig(global_concurrency=999, run_timeout_s=99999, max_retries=99).clamped()
        assert c.global_concurrency == 64
        assert c.run_timeout_s == 3600
        assert c.max_retries == 6

    def test_load_save_roundtrip(self, dbpath):
        RunConfig(global_concurrency=8, min_results=25).save()
        loaded = RunConfig.load()
        assert loaded.global_concurrency == 8 and loaded.min_results == 25


class TestTokenBucket:
    def test_burst_then_cancel(self):
        b = TokenBucket(rpm=1, burst=1)          # 1 token, slow refill
        assert b.acquire() is True                # consumes the burst token
        tok = CancelToken(); tok.cancel()
        assert b.acquire(cancel=tok) is False     # empty + cancelled -> False fast

    def test_capacity_math(self):
        assert TokenBucket(rpm=600).rate == pytest.approx(10.0)


class TestWiden:
    def test_widen_steps(self):
        c = SearchCriteria(keywords=["python", "backend", "senior"], remote=True)
        c2, what = _widen(c)
        assert c2.keywords == ["python", "backend"] and "senior" in what
        c3, what3 = _widen(SearchCriteria(keywords=["python"], remote=True))
        assert c3.remote is None and "remote" in what3.lower()
        assert _widen(SearchCriteria(keywords=["python"], remote=None)) is None


class TestDedupe:
    def test_dedupe_by_fingerprint(self):
        jobs = [_raw("a", 1), _raw("a", 1), _raw("a", 2)]
        assert len(_dedupe(jobs)) == 2


# --------------------------------------------------------------------------- #
class TestEngineRun:
    def _patch(self, monkeypatch, table):
        from core.engine import engine as eng
        monkeypatch.setattr(eng, "run_source",
                            lambda defn, crit, **kw: table[defn.slug])

    def test_streams_and_summarizes(self, dbpath, monkeypatch):
        table = {"greenhouse": _result("greenhouse", 5), "lever": _result("lever", 3)}
        self._patch(monkeypatch, table)
        streamed = []
        eng = ScanEngine(RunConfig(min_results=0), on_event=lambda e: (
            streamed.append(e.source) if e.type == events.SOURCE_RESULT else None))
        summary = eng.run([_defn("greenhouse"), _defn("lever")],
                          SearchCriteria(keywords=["python"]))
        assert summary.status == "completed"
        assert summary.total_jobs == 8 and summary.sources_succeeded == 2
        assert set(streamed) == {"greenhouse", "lever"}
        assert len(summary.jobs) == 8

    def test_priority_browser_last(self, dbpath, monkeypatch):
        table = {"api1": _result("api1", 1), "br": _result("br", 1)}
        self._patch(monkeypatch, table)
        eng = ScanEngine(RunConfig(global_concurrency=1))  # sequential -> order == priority
        summary = eng.run([_defn("br", "browser"), _defn("api1", "api")],
                          SearchCriteria(keywords=["x"]))
        assert [r.slug for r in summary.per_source] == ["api1", "br"]

    def test_checkpoint_and_resume(self, dbpath, monkeypatch):
        table = {"greenhouse": _result("greenhouse", 4), "lever": _result("lever", 2)}
        self._patch(monkeypatch, table)
        eng = ScanEngine(RunConfig())
        summary = eng.run([_defn("greenhouse"), _defn("lever")], SearchCriteria(keywords=["x"]))
        with closing(db.connection.connect()) as conn:
            assert conn.execute("SELECT status FROM run WHERE id=?",
                                (summary.run_id,)).fetchone()["status"] == "completed"
            assert conn.execute("SELECT count(*) n FROM job").fetchone()["n"] == 6
        from core.engine import checkpoint
        assert checkpoint.done_sources(summary.run_id) == {"greenhouse", "lever"}

        # Resume: both sources already done -> a resumed run reruns nothing.
        ran = []
        monkeypatch.setattr("core.engine.engine.run_source",
                            lambda defn, crit, **kw: ran.append(defn.slug) or table[defn.slug])
        eng2 = ScanEngine(RunConfig())
        eng2.run([_defn("greenhouse"), _defn("lever")], SearchCriteria(keywords=["x"]),
                 resume_run_id=summary.run_id)
        assert ran == []  # nothing re-fetched

    def test_cancellation_status(self, dbpath, monkeypatch):
        table = {"a": _result("a", 1)}
        self._patch(monkeypatch, table)
        tok = CancelToken(); tok.cancel()
        eng = ScanEngine(RunConfig(), cancel=tok)
        summary = eng.run([_defn("a")], SearchCriteria(keywords=["x"]))
        assert summary.status == "cancelled"

    def test_widening_triggers_when_below_min(self, dbpath, monkeypatch):
        # Each pass yields 2 jobs; min_results=3 forces a widen round.
        self._patch(monkeypatch, {"a": _result("a", 2)})
        widened = []
        eng = ScanEngine(RunConfig(min_results=3, max_widen_rounds=1),
                         on_event=lambda e: widened.append(e.payload)
                         if e.type == events.WIDENED else None)
        summary = eng.run([_defn("a")], SearchCriteria(keywords=["python", "backend"]))
        assert summary.widen_rounds == 1
        assert widened and "backend" in widened[0]["description"]
