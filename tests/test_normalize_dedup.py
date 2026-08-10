"""Phase 8 — normalization, fingerprint, simhash, URL canonicalization, dedup,
and the destructive fingerprint migration (m005)."""
from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

import db
from core.dedup import cluster, content_fingerprint
from core.dedup.fingerprint import title_key
from core.dedup.simhash import hamming, near, simhash
from core.dedup.urls import canonicalize_url
from core.normalize import normalize_job
from core.normalize.fields import (
    canonical_company,
    company_key,
    infer_seniority,
    normalize_employment,
    parse_location,
    parse_posted,
    parse_salary,
)
from core.scraper.base import RawJob


# --------------------------------------------------------------------------- #
class TestSalary:
    def test_range(self):
        s = parse_salary("$180K – $220K")
        assert (s["min"], s["max"], s["currency"], s["period"]) == (180000, 220000, "USD", "year")

    def test_up_to_and_currency(self):
        s = parse_salary("up to €90,000 per year")
        assert s["max"] == 90000 and s["min"] is None and s["currency"] == "EUR"

    def test_hourly(self):
        s = parse_salary("$50 - $75 / hour")
        assert s["period"] == "hour" and s["max"] == 75

    def test_absent_is_null_never_inferred(self):
        s = parse_salary("")
        assert s["min"] is None and s["max"] is None and s["is_estimated"] is False

    def test_estimated_only_when_stated(self):
        assert parse_salary("~$120,000 estimated")["is_estimated"] is True
        assert parse_salary("$120,000")["is_estimated"] is False


class TestLocation:
    def test_city_state_country(self):
        loc = parse_location("New York, NY (HQ)")
        assert loc["city"] == "New York" and loc["region"] == "NY" and loc["country"] == "USA"

    def test_remote_country(self):
        loc = parse_location("Remote, Italy")
        assert loc["work_mode"] == "remote" and loc["country"] == "Italy"

    def test_hybrid_flag(self):
        assert parse_location("Hybrid - Berlin")["work_mode"] == "hybrid"

    def test_remote_flag_param(self):
        assert parse_location("", remote_flag=True)["work_mode"] == "remote"


class TestDates:
    def test_relative_is_approximate(self):
        r = parse_posted("3 days ago")
        assert r["is_approximate"] and r["iso"].startswith("20")

    def test_iso_passthrough_utc(self):
        r = parse_posted("2026-08-03T16:43:10-04:00")
        assert r["iso"] == "2026-08-03T20:43:10+00:00" and not r["is_approximate"]

    def test_epoch_ms(self):
        assert parse_posted(1690000000000)["iso"].startswith("2023-")

    def test_empty(self):
        assert parse_posted("")["iso"] is None


class TestVocab:
    def test_employment(self):
        assert normalize_employment("Permanent") == "full_time"
        assert normalize_employment("Contractor") == "contract"

    def test_seniority(self):
        assert infer_seniority("Senior Backend Engineer") == "senior"
        assert infer_seniority("Staff SRE") == "principal"
        assert infer_seniority("Software Engineering Intern") == "intern"


class TestCompany:
    def test_strips_suffix_and_yc(self):
        assert canonical_company("Acme Technologies Inc (YC W21)") == "Acme"

    def test_company_key(self):
        assert company_key("Acme, Inc.") == company_key("ACME")


class TestUrls:
    def test_strips_tracking(self):
        u = canonicalize_url("https://Boards.Greenhouse.io/acme/jobs/12345?gh_src=xyz&utm_source=li")
        assert u == "https://boards.greenhouse.io/acme/jobs/12345"

    def test_drops_fragment_and_trailing_slash(self):
        assert canonicalize_url("https://x.com/jobs/1/#apply") == "https://x.com/jobs/1"


class TestSimhash:
    def test_near_identical(self):
        a = simhash("Build backend services in Python and Django at scale. " * 10)
        b = simhash("Build backend services in Python and Django at scale. " * 10 + " Extra.")
        assert near(a, b, threshold=3)

    def test_different(self):
        a = simhash("Registered nurse providing ICU patient care.")
        b = simhash("Senior Rust engineer building distributed databases.")
        assert not near(a, b, threshold=3)


class TestFingerprint:
    def test_same_role_same_fingerprint(self):
        a = content_fingerprint("Acme Inc", "Senior Python Engineer", "Remote")
        b = content_fingerprint("Acme", "Senior  Python   Engineer", "remote")
        assert a == b

    def test_title_key_normalizes(self):
        assert title_key("Senior Python Engineer (Remote)") == "senior python engineer"


class TestCluster:
    def test_cross_source_dedup_keeps_authoritative(self):
        jobs = [
            RawJob(title="Senior Python Engineer", company="Acme Inc", location="Remote, USA",
                   description="Build backend services in Python. " * 20,
                   url="https://boards.greenhouse.io/acme/jobs/1?gh_src=x",
                   source="greenhouse", remote=True),
            RawJob(title="Senior Python Engineer", company="Acme", location="Remote",
                   description="Build backend services in Python. " * 20,
                   url="https://jobicy.com/j/1", source="jobicy", remote=True),
            RawJob(title="Data Engineer", company="Globex", location="Berlin, Germany",
                   description="ETL pipelines.", url="https://jobs.lever.co/globex/2", source="lever"),
        ]
        clusters = cluster([normalize_job(j) for j in jobs])
        assert len(clusters) == 2
        acme = next(c for c in clusters if c.company_name == "Acme")
        assert acme.source == "greenhouse"           # ATS beats aggregator
        assert acme.seen_count == 2
        assert "https://jobicy.com/j/1" in acme.alt_urls
        assert set(acme.sources) == {"greenhouse", "jobicy"}


# --------------------------------------------------------------------------- #
# Migration m005 — fingerprint recompute + merge, preserving user data
# --------------------------------------------------------------------------- #
@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    from db import connection
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    return p


def test_m005_merges_dupes_and_preserves_application(dbpath):
    from db.connection import connect
    from db.migrations import migrate, rollback_to
    # Migrate up to v4 (pre-fingerprint), seed two URL-hash "dupes" of one role.
    with closing(connect()) as conn:
        migrate(conn)  # to latest; then simulate pre-m005 by rolling back m005
        rollback_to(conn, 4)
        # two rows = same role, different URL hashes (the 1.x problem)
        conn.execute("INSERT INTO source(slug,display_name) VALUES ('greenhouse','GH'),('jobicy','Jobicy')")
        gh = conn.execute("SELECT id FROM source WHERE slug='greenhouse'").fetchone()["id"]
        jb = conn.execute("SELECT id FROM source WHERE slug='jobicy'").fetchone()["id"]
        conn.execute("INSERT INTO job(fingerprint,title,company_name,location_city,source_id) "
                     "VALUES ('urlhash_a','Senior Python Engineer','Acme','Berlin',?)", (gh,))
        conn.execute("INSERT INTO job(fingerprint,title,company_name,location_city,source_id) "
                     "VALUES ('urlhash_b','Senior Python Engineer','Acme','Berlin',?)", (jb,))
        loser = conn.execute("SELECT id FROM job WHERE fingerprint='urlhash_b'").fetchone()["id"]
        # the aggregator copy carries the user's saved application
        conn.execute("INSERT INTO application(job_id,status) VALUES (?, 'applied')", (loser,))
        conn.commit()

    db.init_db()  # applies m005

    with closing(connect()) as conn:
        jobs = conn.execute("SELECT fingerprint, company_name FROM job").fetchall()
        assert len(jobs) == 1                       # merged to one canonical role
        new_fp = jobs[0]["fingerprint"]
        assert new_fp == content_fingerprint("Acme", "Senior Python Engineer", "Berlin")
        # the application survived, repointed onto the survivor
        app = conn.execute("SELECT status FROM application").fetchone()
        assert app is not None and app["status"] == "applied"
        # alias table maps both old hashes to the new fingerprint
        aliases = {r["old_fingerprint"]: r["new_fingerprint"]
                   for r in conn.execute("SELECT * FROM fingerprint_alias")}
        assert aliases.get("urlhash_a") == new_fp and aliases.get("urlhash_b") == new_fp


def test_m005_backs_up_nonfresh_db(dbpath):
    from db.connection import connect
    from db.migrations import migrate, rollback_to
    with closing(connect()) as conn:
        migrate(conn)
        rollback_to(conn, 4)
        conn.execute("INSERT INTO job(fingerprint,title,company_name) VALUES ('h','T','C')")
        conn.commit()
    db.init_db()
    assert list(dbpath.parent.glob("*.bak.pre-migration-*"))
