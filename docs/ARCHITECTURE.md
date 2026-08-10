# Drift — Architecture

Living document. Each phase adds its section; this is not a snapshot of a
finished system. Current phases documented: **2 (data layer)**.

---

## Data layer (Phase 2)

### Overview

Storage is SQLite (`db/jobs.db`), accessed through the stdlib `sqlite3` module —
no ORM. Every connection runs in **WAL** mode with **foreign keys enforced** and
a busy timeout. The schema is versioned and applied by an in-repo migration
runner; **FTS5** backs full-text job search.

```
db/
├── connection.py           connect() + pragmas (WAL, FK, busy_timeout); DB_PATH; fts5_available()
├── __init__.py             public API — the exact surface the UI calls, on the new schema
└── migrations/
    ├── __init__.py         runner: migrate(), rollback_to(), current_version(), ALL_MIGRATIONS
    ├── m001_initial_schema.py   14 tables + job_fts + triggers + indexes
    └── m002_import_legacy.py    import 1.x jobs -> job/application/cover_letter, drop legacy
```

### Schema (14 tables + FTS5)

`profile`, `resume`, `resume_version`, `search`, `run`, `source`,
`run_source_result`, `job`, `job_score`, `application`, `cover_letter`,
`blocklist`, `api_key`, `setting`, plus the `job_fts` external-content FTS5
virtual table over `job(title, company_name, description_text)` kept in sync by
AFTER INSERT/UPDATE/DELETE triggers.

`cover_letter` is not in the original spec's table list but is required because
`application.cover_letter_id` must reference something; Phase 4 owns its full
lifecycle. Everything else maps 1:1 to the Phase 2 spec.

Indexes: `job(posted_at)`, `job(company_name)`, `job_score(final_score)`,
`run_source_result(run_id)`, `application(status)`, `cover_letter(job_id)`.
`job(fingerprint)` is covered by its `UNIQUE` constraint.

### Migration framework

A migration is a module exposing `VERSION`, `NAME`, `up(conn)`, `down(conn)`.
`migrate()` applies every pending migration in ascending version order, each in
its own transaction, recording it in a `_migration` table and mirroring the
number into `PRAGMA user_version`. Re-running is a no-op, so `init_db()` is safe
to call on every scan. `rollback_to(version)` runs `down()` in reverse for tests
and recovery; the app never calls it at runtime.

**Adding a migration:** create `db/migrations/mNNN_name.py` and append it to
`ALL_MIGRATIONS`. Never edit an already-shipped migration — write a new one.

### Legacy data migration (m002) — destructive, reversible

The only irreplaceable 1.x data is the user's save/apply/dismiss state and saved
cover letters. m002 imports it into `job` + `application` + `cover_letter`,
keyed by the old URL-fingerprint `job_id`, then drops the legacy `jobs` and
(dead) `seen_jobs` tables.

Reversibility is twofold:
1. `init_db()` **file-copies** a pre-Phase-2 database to
   `db/jobs.db.bak.pre-phase2-<timestamp>` *before* any migration touches it.
2. `m002.down()` reconstructs the legacy `jobs` table from the new schema.

1.x "orphan" rows (status set on a never-fully-recorded job — audit §4.2) are
imported and flagged `job.legacy = 1` rather than dropped.

### Identity and status model

- **Identity.** The 1.x `job_id` was `sha1(url)[:16]`. It is preserved as
  `job.fingerprint`. **Phase 8 replaces this** with a content-based fingerprint
  (`company + title + city + simhash(description)`) so the same job across many
  boards collapses to one record; that migration will recompute every
  fingerprint and keep an alias table so history survives (audit §9.4b).
- **Status.** A `job` with no `application` row is implicitly `new`. Acting on a
  job creates/updates its application; setting it back to `new` deletes the
  application row (un-save). Status vocabulary: `saved`, `applied`, `screening`,
  `interview`, `offer`, `rejected`, `withdrawn`, plus `dismissed` (hide from
  future scans — not a Kanban stage).

### Public API (back-compat surface)

`db/__init__.py` keeps the exact function names the 1.x UI depends on
(`init_db`, `dedupe_by_url`, `known_ids`, `statuses_for`, `dismissed_ids`,
`record_seen`, `set_status`, `save_cover_letter`, `get_cover_letter`,
`mark_jobs_seen`) but reimplements them over the new schema. This is what lets
Phase 2 replace the storage without touching `ui/`. As later phases build proper
repositories per table, these shims stay until the UI is migrated off them.

**Behaviour change worth noting:** 1.x wrote a `score` column on the job row that
nothing ever read. The shim drops that write (scores belong in `job_score`); no
reader is affected.

### Testing

`tests/test_data_layer.py` (24 tests) covers migration idempotency, the full
schema/index shape, FTS5 indexing + delete-trigger consistency, FK cascades, the
legacy import (state preservation, backup creation, orphan flagging), and every
back-compat shim including the full worker→results call sequence. All run against
a throwaway `tmp_path` DB; the real `db/jobs.db` is never touched.
