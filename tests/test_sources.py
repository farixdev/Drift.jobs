"""Phase 6 — declarative source system tests.

Contract tests run each ATS parser against a recorded fixture (a trimmed real
response captured 2026-08-10), so parsing is verified deterministically offline.
Runner, circuit-breaker, robots, and registry behaviour are covered with mocks.
A live smoke test per source is opt-in via DRIFT_LIVE=1.
"""
from __future__ import annotations

import os
from contextlib import closing

import pytest

import db
from core.sources import DEFINITIONS, SearchCriteria, run_source
from core.sources.definitions import ashby, greenhouse, lever, workable


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    from db import connection
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    db.init_db()
    return p


# --------------------------------------------------------------------------- #
# Recorded fixtures (trimmed real shapes)
# --------------------------------------------------------------------------- #
GREENHOUSE_FIX = {"jobs": [{
    "title": "Senior Python Engineer",
    "company_name": "GitLab",
    "location": {"name": "Remote, Italy"},
    "absolute_url": "https://job-boards.greenhouse.io/gitlab/jobs/123",
    "updated_at": "2026-08-03T16:43:10-04:00",
    "content": "&lt;p&gt;Build &lt;b&gt;great&lt;/b&gt; things&lt;/p&gt;",
}]}

LEVER_FIX = [{
    "text": "Analytics Engineer II",
    "categories": {"location": "Stockholm", "commitment": "Permanent"},
    "descriptionPlain": "Do analytics with Python.",
    "hostedUrl": "https://jobs.lever.co/spotify/abc",
    "applyUrl": "https://jobs.lever.co/spotify/abc/apply",
    "createdAt": 1690000000000,
    "workplaceType": "remote",
}]

ASHBY_FIX = {"jobs": [{
    "title": "  Security Engineer, Cloud",
    "location": "New York, NY",
    "isRemote": True,
    "isListed": True,
    "employmentType": "FullTime",
    "descriptionHtml": "<h1>About</h1><p>Secure the cloud</p>",
    "jobUrl": "https://jobs.ashbyhq.com/ramp/x",
    "publishedAt": "2026-04-07T17:12:35.753+00:00",
    "compensation": {"compensationTierSummary": "$180K – $220K"},
}, {"title": "Hidden role", "isListed": False}]}

WORKABLE_FIX = {"name": "Hugging Face", "jobs": [{
    "title": "ML Engineer",
    "city": "Paris", "state": "Île-de-France", "country": "France",
    "telecommuting": True,
    "description": "<p>Democratize good ML</p>",
    "url": "https://apply.workable.com/j/ABC",
    "employment_type": "Full-time",
    "published_on": "2026-07-30",
}]}


class TestParsers:
    def test_greenhouse(self):
        spec = greenhouse.query_mapper(SearchCriteria(companies=["gitlab"]))[0]
        jobs = greenhouse.response_parser(GREENHOUSE_FIX, spec)
        assert len(jobs) == 1
        j = jobs[0]
        assert j.title == "Senior Python Engineer"
        assert j.company == "GitLab"
        assert j.description == "Build great things"   # unescaped + stripped
        assert j.url.endswith("/123")
        assert j.remote is True                         # location contains 'Remote'
        assert j.source == "greenhouse" and j.rich

    def test_lever(self):
        spec = lever.query_mapper(SearchCriteria(companies=["spotify"]))[0]
        jobs = lever.response_parser(LEVER_FIX, spec)
        j = jobs[0]
        assert j.title == "Analytics Engineer II"
        assert j.location == "Stockholm"
        assert j.job_type == "Permanent"
        assert j.url == "https://jobs.lever.co/spotify/abc"
        assert j.remote is True                         # workplaceType == remote
        assert "analytics" in j.description.lower()

    def test_ashby(self):
        spec = ashby.query_mapper(SearchCriteria(companies=["ramp"]))[0]
        jobs = ashby.response_parser(ASHBY_FIX, spec)
        assert len(jobs) == 1                            # unlisted role dropped
        j = jobs[0]
        assert j.title == "Security Engineer, Cloud"     # stripped
        assert j.remote is True
        assert j.salary == "$180K – $220K"
        assert j.description == "About\n\nSecure the cloud" or "Secure the cloud" in j.description

    def test_workable(self):
        spec = workable.query_mapper(SearchCriteria(companies=["huggingface"]))[0]
        jobs = workable.response_parser(WORKABLE_FIX, spec)
        j = jobs[0]
        assert j.company == "Hugging Face"
        assert "Paris" in j.location and "France" in j.location
        assert j.remote is True
        assert j.description == "Democratize good ML"


# --------------------------------------------------------------------------- #
# Runner: filtering, cap, diagnostics, robots-block
# --------------------------------------------------------------------------- #
class TestRunner:
    def test_success_filters_and_caps(self, dbpath, monkeypatch):
        from core.sources import http, robots
        monkeypatch.setattr(robots, "allowed", lambda url: True)
        monkeypatch.setattr(http, "get", lambda *a, **k: http.Fetch(
            ok=True, status=200, json=GREENHOUSE_FIX))
        crit = SearchCriteria(keywords=["python"], companies=["gitlab"], max_per_source=5)
        r = run_source(DEFINITIONS["greenhouse"], crit)
        assert r.status == "done"
        assert r.http_status is None  # success path
        assert all("python" in (j.title + j.description).lower() for j in r.jobs)
        assert len(r.jobs) <= 5

    def test_robots_disallow_blocks(self, dbpath, monkeypatch):
        from core.sources import http, robots
        monkeypatch.setattr(robots, "allowed", lambda url: False)
        called = {"n": 0}
        monkeypatch.setattr(http, "get", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
        r = run_source(DEFINITIONS["greenhouse"], SearchCriteria(companies=["gitlab"]))
        assert r.status == "blocked"
        assert called["n"] == 0  # never fetched a disallowed URL

    def test_http_failure_surfaces_diagnostics(self, dbpath, monkeypatch):
        from core.sources import http, robots
        monkeypatch.setattr(robots, "allowed", lambda url: True)
        monkeypatch.setattr(http, "get", lambda *a, **k: http.Fetch(
            ok=False, status=503, error_class="HTTP503", error_detail="down"))
        r = run_source(DEFINITIONS["lever"], SearchCriteria(companies=["spotify"]))
        assert r.status == "failed"
        assert r.http_status == 503 and r.error_class == "HTTP503"
        assert r.finished_at  # timestamp present


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #
class TestCircuitBreaker:
    def test_opens_after_threshold_and_resets(self, dbpath):
        from core.sources import health
        defn = DEFINITIONS["ashby"]
        health.ensure_source(defn)
        assert health.allow(defn.slug) is True
        for _ in range(health.FAILURE_THRESHOLD):
            health.record_failure(defn.slug, "boom")
        assert health.allow(defn.slug) is False          # breaker open
        assert health.health(defn.slug)["health_status"] == "disabled"
        health.record_success(defn.slug)
        assert health.allow(defn.slug) is True            # closed again
        assert health.health(defn.slug)["consecutive_failures"] == 0


# --------------------------------------------------------------------------- #
# Registry & removals
# --------------------------------------------------------------------------- #
class TestRegistry:
    def test_ats_and_aggregator_sources_defined(self):
        assert {"greenhouse", "lever", "ashby", "workable"} <= set(DEFINITIONS)   # Tier 1 ATS
        assert {"himalayas", "workingnomads"} <= set(DEFINITIONS)                 # Tier 2 aggregators

    def test_bridge_wraps_declarative_source(self):
        from core.scraper import get_scraper
        from core.sources.bridge import DeclarativeScraper
        assert isinstance(get_scraper("greenhouse"), DeclarativeScraper)

    def test_noncompliant_sources_removed(self):
        from core.scraper import SCRAPERS, SOURCES
        removed = {"linkedin", "indeed", "ziprecruiter", "google", "bing"}
        assert not (removed & set(SCRAPERS))
        assert not (removed & {s["key"] for s in SOURCES})


# --------------------------------------------------------------------------- #
# Opt-in live smoke test (real network) — DRIFT_LIVE=1
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(os.environ.get("DRIFT_LIVE") != "1", reason="set DRIFT_LIVE=1 for live")
class TestLive:
    @pytest.mark.parametrize("slug", ["greenhouse", "lever", "ashby", "workable"])
    def test_live_source_returns_jobs(self, dbpath, slug):
        r = run_source(DEFINITIONS[slug], SearchCriteria(keywords=["engineer"], max_per_source=10))
        assert r.status == "done", f"{slug}: {r.error_class} {r.error_detail}"
        assert r.jobs, f"{slug} returned no jobs"
