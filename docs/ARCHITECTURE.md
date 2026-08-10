# Drift — Architecture

Living document. Each phase adds its section; this is not a snapshot of a
finished system. Current phases documented: **2 (data layer)**, **3 (AI layer)**.

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

---

## AI provider layer (Phase 3)

Bring-your-own-key, 8 providers, single interface, called over raw HTTP. Full
detail (live verification, key-safety rules, routing) is in
[docs/AI_PROVIDERS.md](AI_PROVIDERS.md); the module map and integration points:

```
core/ai/            registry, errors, types, http, base, openai_compat, native,
                    factory, keystore, models_fallback, routing, cost, cache,
                    budget, manager
core/ai_engine.py   thin task-shaped facade (parse_resume / score_jobs_batch /
                    generate_cover_letter) — same 1.x surface, now over LLMManager
```

**Integration.** `core/ai_engine.py` keeps the exact functions `matcher.py`,
`ui/worker.py`, and `ui/dialogs.py` already call, so no UI or matcher code
changed. Under the hood each function is a task: `parse_resume` → `resume_parse`,
`score_jobs_batch` → `job_rerank`, `generate_cover_letter` → `cover_letter`. The
old Groq-only OpenAI client is gone; Groq is one provider behind the router and
remains the default route, so behaviour is preserved.

**Storage tie-ins.** Migration `m003` adds `llm_cache` (prompt-response cache) and
`llm_usage` (cost ledger). Routing, pricing, and cache config are JSON values in
the `setting` table via `db.get_setting` / `db.set_setting`. Keys live in the OS
keychain, never in the database.

**Verified live.** All 8 model endpoints probed 2026-08-10; the full stack
(list_models → structured completion with schema repair → cost metering) was run
end-to-end against Groq with the install's real key.

---

## Execution engine (Phase 7)

The concurrent orchestration layer between search criteria and sources
(`core/engine/`). Replaces the 1.x `ScanWorker` fan-out.

```
core/engine/
├── config.py        RunConfig (concurrency, timeouts, min/max results, proxy) + clamp/load/save
├── cancellation.py  CancelToken (cooperative, threading.Event) + Cancelled
├── ratelimit.py     TokenBucket + DomainLimiter (per-host bucket + concurrency semaphore)
├── events.py        RunEvent stream + RunSummary
├── checkpoint.py    run / run_source_result persistence + raw-job upsert (durable partials)
└── engine.py        ScanEngine.run() — pool, priority, streaming, widening
```

**What it does:** orders sources by priority (clean APIs first, browser last),
runs them through a bounded pool (default 12, 1–64) with per-domain token-bucket
rate limiting, streams each source's results the moment it returns (`on_event`),
persists a checkpoint after every source, honours a global timeout and per-source
timeout, and supports cooperative cancellation. Retries (429/5xx/timeout only,
backoff + full jitter, honouring Retry-After) live in `core/sources/http.py`; the
per-source circuit breaker is reused from `core/sources/health.py`. When
`min_results` isn't met it **widens** the query (drops the most-specific keyword,
then the remote filter) and reruns, reporting exactly what was relaxed.

**Uniform sources:** the engine runs both declarative ATS definitions
(`run_source`) and the legacy first-party feeds (`run_legacy`, wrapped as
definitions in `core/sources/legacy.py`) through the same pool/priority/breaker/
streaming path. `resolve_selection(keys)` maps UI source keys to definitions.

**Integration:** `ScanWorker` (`ui/worker.py`) builds a `SearchCriteria`, runs
the engine, and forwards its event stream to the **live run view**
(`ui/screen_run.py`) — per-source rows (queued → running → done/failed/blocked)
with live counts, an overall progress bar, elapsed time, a collapsing log, and a
cancel button, built on the Phase-1 components. Checkpoints land in the Phase-2
`run` / `run_source_result` tables; `done_sources(run_id)` lets a resumed run skip
completed sources.

**Verified:** live run of the 4 ATS sources through the engine (81 unique jobs,
streamed, checkpointed); full worker→engine→run-view wiring (66 jobs, source
events). 11 engine tests cover config, token bucket, cancellation, priority,
streaming, checkpoint+resume, and widening.

---

## Normalization, dedup & ranking (Phase 8)

```
core/normalize/   fields (salary/date/location/vocab/company) + normalize_job -> NormalizedJob
core/dedup/       urls (canonicalize) · simhash · fingerprint (content) · cluster
core/ranking/     lexical (BM25) · semantic (embeddings) · blend (weights/freshness/blocklist) · rank_jobs
```

**Identity is content-based** (migration m005): `fingerprint = normalize(company) +
title + city`, replacing the 1.x URL hash so the same role on many boards collapses
to one record. m005 recomputes every stored fingerprint, keeps a
`fingerprint_alias(old→new)` table, and merges duplicate rows — repointing
application/cover_letter/job_score onto the most authoritative survivor so user
history is preserved. `init_db()` file-backs-up any non-fresh DB first.

**Normalization** maps each raw result to the canonical schema — salary
min/max/currency/period (null when unstated, never inferred), UTC dates with an
approximate flag for relative strings, structured location + work-mode vocab,
employment/seniority vocab, canonical company. **Dedup** clusters by content
fingerprint (+ simhash near-merge for title/format variants), keeps the most
authoritative + complete record (ATS > aggregator > feed), stores alternate apply
URLs, and stamps `seen_count` ("seen on N sites" badge).

**Ranking** is three stages: (1) lexical BM25 over the candidate corpus; (2)
semantic cosine of cached embeddings (skipped gracefully when no embedder is
configured — Ollama/OpenAI/…); (3) LLM rerank of the top 100, batched 20/call,
returning a score + one-sentence rationale. The final score blends the available
stages by user weights × a freshness decay, filtered against the blocklist. Every
Job carries per-dimension sub-scores + rationale, so the card always explains the
number (lexical + freshness at minimum). m006 adds the embedding cache.

**Pipeline:** the worker runs engine → `normalize_and_cluster` → `rank_jobs` →
persist (content fingerprints; checkpoint and final write share identity, no dup
rows). Verified live: 52 raw → 41 roles, and a 3-stage rank with real Groq rerank
producing explainable sub-scores + rationales.
