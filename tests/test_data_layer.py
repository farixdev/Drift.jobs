"""Phase 2 — data layer tests.

Covers the migration framework, the target schema, FTS5, the destructive legacy
import (m002), and the back-compat shims the 1.x UI still calls. Every test runs
against a throwaway DB in a tmp_path; the real db/jobs.db is never touched.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

import db
from db import connection
from db.connection import connect, fts5_available
from db.migrations import (
    ALL_MIGRATIONS,
    LATEST_VERSION,
    current_version,
    migrate,
    rollback_to,
)
from models import (
    STATUS_APPLIED,
    STATUS_DISMISSED,
    STATUS_NEW,
    STATUS_SAVED,
    Job,
)

EXPECTED_TABLES = {
    "profile", "resume", "resume_version", "search", "run", "source",
    "run_source_result", "job", "job_score", "application", "cover_letter",
    "blocklist", "api_key", "setting",
}


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    """Point the whole data layer at a fresh temp DB for the duration of a test."""
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    return p


def _table_names(conn):
    return {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #
def test_fts5_is_available(dbpath):
    with closing(connect()) as conn:
        assert fts5_available(conn) is True


def test_connection_pragmas(dbpath):
    with closing(connect()) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# --------------------------------------------------------------------------- #
# Migration framework
# --------------------------------------------------------------------------- #
def test_migrate_creates_full_schema(dbpath):
    with closing(connect()) as conn:
        applied = migrate(conn)
        assert applied == [m.VERSION for m in ALL_MIGRATIONS]
        assert current_version(conn) == LATEST_VERSION
        assert EXPECTED_TABLES <= _table_names(conn)
        # FTS5 virtual table + shadow tables present.
        assert "job_fts" in _table_names(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION


def test_migrate_is_idempotent(dbpath):
    with closing(connect()) as conn:
        migrate(conn)
        second = migrate(conn)  # nothing pending
        assert second == []
        assert current_version(conn) == LATEST_VERSION


def test_expected_indexes_exist(dbpath):
    with closing(connect()) as conn:
        migrate(conn)
        idx = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert {"idx_job_posted_at", "idx_job_company",
                "idx_job_score_final", "idx_application_status"} <= idx


def test_rollback_removes_new_schema(dbpath):
    with closing(connect()) as conn:
        migrate(conn)
        rollback_to(conn, 0)
        assert current_version(conn) == 0
        names = _table_names(conn)
        assert not (EXPECTED_TABLES & names)  # all target tables gone


# --------------------------------------------------------------------------- #
# FTS5 search + sync triggers
# --------------------------------------------------------------------------- #
def test_fts_indexes_and_tracks_jobs(dbpath):
    with closing(connect()) as conn:
        migrate(conn)
        conn.execute(
            "INSERT INTO job(fingerprint, title, company_name, description_text) "
            "VALUES ('fp1', 'Senior Python Engineer', 'Acme', 'Django and FastAPI')"
        )
        conn.commit()
        hit = conn.execute(
            "SELECT j.title FROM job_fts f JOIN job j ON j.id=f.rowid "
            "WHERE job_fts MATCH 'python'"
        ).fetchone()
        assert hit["title"] == "Senior Python Engineer"

        # Delete trigger keeps the index consistent (external-content FTS).
        conn.execute("DELETE FROM job WHERE fingerprint='fp1'")
        conn.commit()
        gone = conn.execute(
            "SELECT count(*) AS n FROM job_fts WHERE job_fts MATCH 'python'"
        ).fetchone()
        assert gone["n"] == 0


# --------------------------------------------------------------------------- #
# Foreign-key cascades
# --------------------------------------------------------------------------- #
def test_deleting_job_cascades(dbpath):
    with closing(connect()) as conn:
        migrate(conn)
        conn.execute("INSERT INTO job(fingerprint, title) VALUES ('fp1', 'X')")
        jid = conn.execute("SELECT id FROM job WHERE fingerprint='fp1'").fetchone()["id"]
        conn.execute("INSERT INTO application(job_id, status) VALUES (?, 'saved')", (jid,))
        conn.execute("INSERT INTO cover_letter(job_id, body) VALUES (?, 'hi')", (jid,))
        conn.commit()
        conn.execute("DELETE FROM job WHERE id=?", (jid,))
        conn.commit()
        assert conn.execute("SELECT count(*) AS n FROM application").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM cover_letter").fetchone()["n"] == 0


# --------------------------------------------------------------------------- #
# Legacy import (m002) — the destructive, data-preserving migration
# --------------------------------------------------------------------------- #
def _make_legacy_db(path):
    """Build a 1.x-shaped database with realistic rows, including an orphan."""
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute(
            """CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY, url TEXT, title TEXT, company TEXT,
                location TEXT, source TEXT, score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'new', cover_letter TEXT DEFAULT '',
                first_seen TEXT, last_seen TEXT)"""
        )
        conn.execute(
            "CREATE TABLE seen_jobs (url TEXT PRIMARY KEY, title TEXT, company TEXT,"
            " source TEXT, scraped_at TEXT)"
        )
        conn.executemany(
            "INSERT INTO jobs (job_id,url,title,company,location,source,score,status,"
            "cover_letter,first_seen,last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("fp_saved", "https://x.com/1", "Backend Eng", "Acme", "Remote",
                 "remoteok", 88, "saved", "", "2026-01-01", "2026-01-02"),
                ("fp_applied", "https://x.com/2", "Data Eng", "Globex", "NYC",
                 "themuse", 75, "applied", "Dear team...", "2026-01-03", "2026-01-04"),
                ("fp_dismissed", "https://x.com/3", "Sales", "Initech", "",
                 "hn", 12, "dismissed", "", "2026-01-05", "2026-01-06"),
                ("fp_new", "https://x.com/4", "SRE", "Umbrella", "Remote",
                 "arbeitnow", 60, "new", "", "2026-01-07", "2026-01-08"),
                # orphan: status set on a job that was never fully recorded
                ("fp_orphan", "", "", "", "", "", 0, "saved", "", None, None),
            ],
        )
        conn.commit()


def test_legacy_import_preserves_user_state(dbpath):
    _make_legacy_db(dbpath)
    db.init_db()  # backup + migrate (incl. m005 fingerprint recompute) + import

    with closing(connect()) as conn:
        # m005 recomputed the URL-hash fingerprints into content fingerprints;
        # the alias table maps the old ids to the new ones. State must survive.
        alias = {r["old_fingerprint"]: r["new_fingerprint"]
                 for r in conn.execute("SELECT * FROM fingerprint_alias")}

        def new_fp(old):
            return alias.get(old, old)

        # Every legacy job is still present (now under its content fingerprint).
        fps = {r["fingerprint"] for r in conn.execute("SELECT fingerprint FROM job")}
        assert {new_fp(x) for x in ("fp_saved", "fp_applied", "fp_dismissed",
                                    "fp_new", "fp_orphan")} <= fps

        def status(old):
            row = conn.execute(
                "SELECT a.status FROM application a JOIN job j ON j.id=a.job_id "
                "WHERE j.fingerprint=?", (new_fp(old),)
            ).fetchone()
            return row["status"] if row else None

        assert status("fp_saved") == STATUS_SAVED
        assert status("fp_applied") == STATUS_APPLIED
        assert status("fp_dismissed") == STATUS_DISMISSED
        assert status("fp_new") is None      # implicit 'new' -> no application row

        applied_at = conn.execute(
            "SELECT a.applied_at FROM application a JOIN job j ON j.id=a.job_id "
            "WHERE j.fingerprint=?", (new_fp("fp_applied"),)
        ).fetchone()["applied_at"]
        assert applied_at == "2026-01-04"

        # Cover letter preserved and linked (looked up by the new fingerprint).
        assert db.get_cover_letter(new_fp("fp_applied")) == "Dear team..."

        # Orphan flagged legacy=1; full rows are legacy=0.
        assert conn.execute("SELECT legacy FROM job WHERE fingerprint=?",
                            (new_fp("fp_orphan"),)).fetchone()["legacy"] == 1
        assert conn.execute("SELECT legacy FROM job WHERE fingerprint=?",
                            (new_fp("fp_saved"),)).fetchone()["legacy"] == 0

        # Legacy tables are gone.
        assert "jobs" not in _table_names(conn)
        assert "seen_jobs" not in _table_names(conn)


def test_legacy_import_writes_a_backup(dbpath):
    _make_legacy_db(dbpath)
    db.init_db()
    backups = list(dbpath.parent.glob("*.bak.pre-migration-*"))
    assert len(backups) == 1
    # Backup still holds the original legacy schema.
    with closing(sqlite3.connect(str(backups[0]))) as conn:
        assert conn.execute(
            "SELECT count(*) FROM jobs"
        ).fetchone()[0] == 5


def test_fresh_install_needs_no_backup(dbpath):
    db.init_db()  # no legacy DB present
    assert list(dbpath.parent.glob("*.bak.pre-migration-*")) == []
    assert db.schema_version() == LATEST_VERSION


# --------------------------------------------------------------------------- #
# Back-compat shims — the exact surface ui/worker.py and ui/screen_results.py use
# --------------------------------------------------------------------------- #
def _job(fp_url, title="Engineer", company="Acme", **kw):
    return Job(title=title, company=company, location=kw.get("location", "Remote"),
               job_type=kw.get("job_type", "Remote"), url=fp_url, source=kw.get("source", "remoteok"),
               description=kw.get("description", "Python, Django"), remote=kw.get("remote", True))


def test_record_seen_and_known_ids(dbpath):
    db.init_db()
    jobs = [_job("https://x.com/a"), _job("https://x.com/b")]
    db.record_seen(jobs)
    known = db.known_ids()
    assert {j.job_id for j in jobs} <= known


def test_record_seen_is_upsert_not_duplicate(dbpath):
    db.init_db()
    j = _job("https://x.com/a")
    db.record_seen([j])
    db.record_seen([j])  # same fingerprint again
    with closing(connect()) as conn:
        n = conn.execute("SELECT count(*) AS n FROM job WHERE fingerprint=?",
                         (j.job_id,)).fetchone()["n"]
    assert n == 1


def test_status_lifecycle(dbpath):
    db.init_db()
    j = _job("https://x.com/a")
    db.record_seen([j])
    fp = j.job_id

    # default: no application -> 'new'
    assert db.statuses_for([fp])[fp] == STATUS_NEW

    db.set_status(fp, STATUS_SAVED)
    assert db.statuses_for([fp])[fp] == STATUS_SAVED

    db.set_status(fp, STATUS_APPLIED)
    assert db.statuses_for([fp])[fp] == STATUS_APPLIED

    db.set_status(fp, STATUS_DISMISSED)
    assert db.statuses_for([fp])[fp] == STATUS_DISMISSED
    assert fp in db.dismissed_ids()

    # setting 'new' un-sets (removes the application row)
    db.set_status(fp, STATUS_NEW)
    assert db.statuses_for([fp])[fp] == STATUS_NEW
    assert fp not in db.dismissed_ids()


def test_set_status_on_unknown_job_creates_legacy_row(dbpath):
    db.init_db()
    db.set_status("never_seen_fp", STATUS_SAVED)  # no prior record_seen
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT legacy FROM job WHERE fingerprint='never_seen_fp'"
        ).fetchone()
    assert row is not None and row["legacy"] == 1
    assert db.statuses_for(["never_seen_fp"])["never_seen_fp"] == STATUS_SAVED


def test_cover_letter_round_trip(dbpath):
    db.init_db()
    j = _job("https://x.com/a")
    db.record_seen([j])
    db.save_cover_letter(j.job_id, "Dear hiring manager, ...")
    assert db.get_cover_letter(j.job_id) == "Dear hiring manager, ..."
    # latest wins
    db.save_cover_letter(j.job_id, "Second draft")
    assert db.get_cover_letter(j.job_id) == "Second draft"


def test_dedupe_by_url_is_pure(dbpath):
    jobs = [_job("https://x.com/a"), _job("https://x.com/a"), _job("https://x.com/b")]
    out = db.dedupe_by_url(jobs)
    assert len(out) == 2
