"""Migration 001 — the full Drift target schema.

Creates all 14 core tables, the FTS5 search index over `job`, its sync triggers,
and the indexes the query paths need. This is additive: on an existing 1.x
install it runs alongside the legacy `jobs`/`seen_jobs` tables, which m002 then
imports from and drops. Nothing here touches legacy data.

Table creation is ordered so every FOREIGN KEY target already exists, which
keeps the schema readable even though SQLite would tolerate forward references.
"""
from __future__ import annotations

import sqlite3

VERSION = 1
NAME = "initial_schema"

# Each element is ONE complete statement (triggers contain internal semicolons,
# so they must stay whole — never naively split this on ";").
_TABLES: list[str] = [
    # -- profile: single-user identity + search defaults -------------------
    """
    CREATE TABLE profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        location TEXT NOT NULL DEFAULT '',
        work_authorization TEXT NOT NULL DEFAULT '',
        target_titles_json TEXT NOT NULL DEFAULT '[]',
        target_salary_min INTEGER,
        target_salary_max INTEGER,
        salary_currency TEXT NOT NULL DEFAULT 'USD',
        willing_to_relocate INTEGER NOT NULL DEFAULT 0,
        timezone TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # -- resume: multiple resumes per profile ------------------------------
    """
    CREATE TABLE resume (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER REFERENCES profile(id) ON DELETE CASCADE,
        label TEXT NOT NULL DEFAULT 'My Resume',
        source_path TEXT NOT NULL DEFAULT '',
        source_blob BLOB,
        raw_text TEXT NOT NULL DEFAULT '',
        parsed_json TEXT NOT NULL DEFAULT '{}',
        is_default INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # -- source: adapter registry + health --------------------------------
    """
    CREATE TABLE source (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL DEFAULT '',
        category TEXT NOT NULL DEFAULT '',
        adapter_type TEXT NOT NULL DEFAULT 'api',
        base_url TEXT NOT NULL DEFAULT '',
        auth_required INTEGER NOT NULL DEFAULT 0,
        rate_limit_rpm INTEGER NOT NULL DEFAULT 60,
        robots_allowed INTEGER,
        is_enabled INTEGER NOT NULL DEFAULT 1,
        health_status TEXT NOT NULL DEFAULT 'unknown',
        last_success_at TEXT,
        last_error TEXT NOT NULL DEFAULT '',
        consecutive_failures INTEGER NOT NULL DEFAULT 0
    )
    """,
    # -- job: canonical listing -------------------------------------------
    """
    CREATE TABLE job (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL DEFAULT '',
        company_name TEXT NOT NULL DEFAULT '',
        company_domain TEXT NOT NULL DEFAULT '',
        location_raw TEXT NOT NULL DEFAULT '',
        location_city TEXT NOT NULL DEFAULT '',
        location_region TEXT NOT NULL DEFAULT '',
        location_country TEXT NOT NULL DEFAULT '',
        work_mode TEXT NOT NULL DEFAULT 'unspecified',
        employment_type TEXT NOT NULL DEFAULT '',
        seniority TEXT NOT NULL DEFAULT '',
        salary_min INTEGER,
        salary_max INTEGER,
        salary_currency TEXT NOT NULL DEFAULT '',
        salary_period TEXT NOT NULL DEFAULT '',
        salary_is_estimated INTEGER NOT NULL DEFAULT 0,
        description_html TEXT NOT NULL DEFAULT '',
        description_text TEXT NOT NULL DEFAULT '',
        requirements_json TEXT NOT NULL DEFAULT '[]',
        posted_at TEXT,
        posted_at_is_approximate INTEGER NOT NULL DEFAULT 0,
        expires_at TEXT,
        apply_url TEXT NOT NULL DEFAULT '',
        canonical_url TEXT NOT NULL DEFAULT '',
        alt_urls_json TEXT NOT NULL DEFAULT '[]',
        source_id INTEGER REFERENCES source(id) ON DELETE SET NULL,
        first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
        is_active INTEGER NOT NULL DEFAULT 1,
        raw_json TEXT NOT NULL DEFAULT '{}',
        legacy INTEGER NOT NULL DEFAULT 0
    )
    """,
    # -- resume_version: tailored variants; never overwrite base -----------
    """
    CREATE TABLE resume_version (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id INTEGER NOT NULL REFERENCES resume(id) ON DELETE CASCADE,
        tailored_for_job_id INTEGER REFERENCES job(id) ON DELETE SET NULL,
        label TEXT NOT NULL DEFAULT '',
        content_json TEXT NOT NULL DEFAULT '{}',
        generated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # -- cover_letter: drafted letters (application.cover_letter_id -> here) -
    """
    CREATE TABLE cover_letter (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER REFERENCES job(id) ON DELETE CASCADE,
        body TEXT NOT NULL DEFAULT '',
        tone TEXT NOT NULL DEFAULT '',
        model_used TEXT NOT NULL DEFAULT '',
        generated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # -- search: saved query object ---------------------------------------
    """
    CREATE TABLE search (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL DEFAULT 'Untitled search',
        query_json TEXT NOT NULL DEFAULT '{}',
        schedule_cron TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        last_run_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # -- run: one execution of a search -----------------------------------
    """
    CREATE TABLE run (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_id INTEGER REFERENCES search(id) ON DELETE SET NULL,
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at TEXT,
        status TEXT NOT NULL DEFAULT 'running',
        jobs_found INTEGER NOT NULL DEFAULT 0,
        jobs_new INTEGER NOT NULL DEFAULT 0,
        sources_attempted INTEGER NOT NULL DEFAULT 0,
        sources_succeeded INTEGER NOT NULL DEFAULT 0,
        sources_failed INTEGER NOT NULL DEFAULT 0,
        config_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    # -- run_source_result: per-source outcome within a run ----------------
    """
    CREATE TABLE run_source_result (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
        source_id INTEGER REFERENCES source(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        duration_ms INTEGER,
        jobs_returned INTEGER NOT NULL DEFAULT 0,
        error_class TEXT NOT NULL DEFAULT '',
        error_detail TEXT NOT NULL DEFAULT '',
        http_status INTEGER
    )
    """,
    # -- job_score: per (job,resume) score with full decomposition ---------
    """
    CREATE TABLE job_score (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
        resume_id INTEGER REFERENCES resume(id) ON DELETE CASCADE,
        keyword_score REAL,
        semantic_score REAL,
        llm_score REAL,
        final_score REAL,
        freshness_factor REAL NOT NULL DEFAULT 1.0,
        explanation_json TEXT NOT NULL DEFAULT '{}',
        scored_at TEXT NOT NULL DEFAULT (datetime('now')),
        model_used TEXT NOT NULL DEFAULT '',
        UNIQUE(job_id, resume_id)
    )
    """,
    # -- application: tracker (one per job) --------------------------------
    """
    CREATE TABLE application (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL UNIQUE REFERENCES job(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'saved',
        applied_at TEXT,
        resume_version_id INTEGER REFERENCES resume_version(id) ON DELETE SET NULL,
        cover_letter_id INTEGER REFERENCES cover_letter(id) ON DELETE SET NULL,
        notes TEXT NOT NULL DEFAULT '',
        next_action TEXT NOT NULL DEFAULT '',
        next_action_due TEXT,
        contact_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # -- blocklist ---------------------------------------------------------
    """
    CREATE TABLE blocklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        value TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(type, value)
    )
    """,
    # -- api_key: encrypted at rest (Phase 3 owns the crypto) --------------
    """
    CREATE TABLE api_key (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        encrypted_value TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_verified_at TEXT,
        UNIQUE(provider, label)
    )
    """,
    # -- setting: single-row-per-key config store --------------------------
    """
    CREATE TABLE setting (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL DEFAULT 'null',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
]

# FTS5 over the human-searchable job fields, external-content mapped to job.id.
_FTS: list[str] = [
    """
    CREATE VIRTUAL TABLE job_fts USING fts5(
        title, company_name, description_text,
        content='job', content_rowid='id'
    )
    """,
    """
    CREATE TRIGGER job_fts_ai AFTER INSERT ON job BEGIN
        INSERT INTO job_fts(rowid, title, company_name, description_text)
        VALUES (new.id, new.title, new.company_name, new.description_text);
    END
    """,
    """
    CREATE TRIGGER job_fts_ad AFTER DELETE ON job BEGIN
        INSERT INTO job_fts(job_fts, rowid, title, company_name, description_text)
        VALUES ('delete', old.id, old.title, old.company_name, old.description_text);
    END
    """,
    """
    CREATE TRIGGER job_fts_au AFTER UPDATE ON job BEGIN
        INSERT INTO job_fts(job_fts, rowid, title, company_name, description_text)
        VALUES ('delete', old.id, old.title, old.company_name, old.description_text);
        INSERT INTO job_fts(rowid, title, company_name, description_text)
        VALUES (new.id, new.title, new.company_name, new.description_text);
    END
    """,
]

# job(fingerprint) is already covered by its UNIQUE index; the rest are hot paths.
_INDEXES: list[str] = [
    "CREATE INDEX idx_job_posted_at ON job(posted_at)",
    "CREATE INDEX idx_job_company ON job(company_name)",
    "CREATE INDEX idx_job_score_final ON job_score(final_score)",
    "CREATE INDEX idx_rsr_run ON run_source_result(run_id)",
    "CREATE INDEX idx_application_status ON application(status)",
    "CREATE INDEX idx_cover_letter_job ON cover_letter(job_id)",
]

# Every object this migration creates, for a clean down().
_DROP_ORDER: list[str] = [
    "DROP TRIGGER IF EXISTS job_fts_au",
    "DROP TRIGGER IF EXISTS job_fts_ad",
    "DROP TRIGGER IF EXISTS job_fts_ai",
    "DROP TABLE IF EXISTS job_fts",
    "DROP TABLE IF EXISTS setting",
    "DROP TABLE IF EXISTS api_key",
    "DROP TABLE IF EXISTS blocklist",
    "DROP TABLE IF EXISTS application",
    "DROP TABLE IF EXISTS job_score",
    "DROP TABLE IF EXISTS run_source_result",
    "DROP TABLE IF EXISTS run",
    "DROP TABLE IF EXISTS search",
    "DROP TABLE IF EXISTS cover_letter",
    "DROP TABLE IF EXISTS resume_version",
    "DROP TABLE IF EXISTS job",
    "DROP TABLE IF EXISTS source",
    "DROP TABLE IF EXISTS resume",
    "DROP TABLE IF EXISTS profile",
]


def up(conn: sqlite3.Connection) -> None:
    from db.connection import fts5_available

    if not fts5_available(conn):
        raise RuntimeError(
            "This SQLite build lacks FTS5, which Drift requires for job search. "
            "Use a Python whose sqlite3 is compiled with ENABLE_FTS5."
        )
    for statement in _TABLES + _FTS + _INDEXES:
        conn.execute(statement)


def down(conn: sqlite3.Connection) -> None:
    for statement in _DROP_ORDER:
        conn.execute(statement)
