# Runbook

Operational guide for running, testing, and troubleshooting Drift.

## Run the app
```bash
python main.py
```
Windows-first (uses the OS keychain via pywin32; falls back to AES-256-GCM
elsewhere). No API key required — Drift scores locally out of the box; add a
provider key in Settings for AI scoring, tailoring, and cover letters.

## Environment
- Python 3.12+ (developed on 3.14). Dependencies pinned in `requirements.txt`.
- Install: `pip install -r requirements-dev.txt` (dev) or `-r requirements.txt` (runtime).
- The database lives at `db/jobs.db` (WAL mode). It is created and migrated
  automatically on first run; a non-fresh DB is backed up before any migration.

## Tests
```bash
python -m pytest                 # full suite
DRIFT_LIVE=1 python -m pytest tests/test_sources.py::TestLive   # opt-in live source smoke
```
On the Bash tool prefix with `PYTHONIOENCODING=utf-8`. UI tests run under Qt;
CI uses `QT_QPA_PLATFORM=offscreen`. Note: the offscreen platform renders text
blank — for a real screenshot, run with `QT_QPA_PLATFORM=windows`.

## CI
`.github/workflows/ci.yml` runs the test suite (offscreen Qt), the full-tree
secret scan (`scripts/check_secrets.py --all`), and a `pip-audit` dependency audit
on every push/PR to `main`.

## Secret scanning
A pre-commit hook blocks committing key-shaped tokens. Install once:
```bash
python scripts/check_secrets.py --install
```

## Migrations
Schema is versioned in `db/migrations/`. To add one, create `mNNN_name.py` and
append it to `ALL_MIGRATIONS` — never edit a shipped migration. `init_db()` applies
pending migrations idempotently and backs up a non-fresh DB first.

## Adding a source
Drop a module exposing `DEFINITION` into `core/sources/definitions/` and list it in
that package's `ALL`. No engine code changes. Verify it live (real request, real
jobs) before shipping — the `DRIFT_LIVE=1` smoke test enforces this. If an endpoint
is robots-disallowed, gated, or dead, log it in `docs/SOURCES_REJECTED.md`.

## Troubleshooting
- **A scan finds nothing:** check the run view / Runs page — each source shows
  its status, HTTP code, and error class. A `blocked` source is robots-disallowed;
  a `circuit_open` source tripped its breaker (5 failures → 1h cool-off).
- **AI features unavailable:** Settings → add a provider key. `has_api_key()` is
  false until a key is stored or `.env` has a legacy `GROQ_API_KEY`.
- **Semantic ranking "off":** it needs an embedding provider (Ollama running
  locally, or an OpenAI/Gemini/Mistral key). Without one it degrades gracefully.
- **DB locked:** WAL + a 5s busy timeout handle concurrency; if it persists, close
  other processes holding `db/jobs.db`.

## Performance budgets (targets)
- Dashboard interactive < 1.5s on a warm cache.
- Virtualised job table smooth at 5,000 rows (QTableView is natively virtualised).
- A 40-source API-only run completing under ~3 min (bounded pool + per-domain
  rate limits; browser tiers excluded).
These are targets; they are not yet enforced by an automated perf gate.

## Accessibility
Full keyboard navigation, a visible accent focus ring, and WCAG-AA-oriented
contrast tokens are built into the design system. A formal axe/keyboard-only audit
per route is outstanding.
