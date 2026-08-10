# Drift — Repository Audit (Phase 0)

**Audited:** 2026-08-10 · **Commit:** `ada5798` · **Branch:** `main` (clean)
**Auditor note:** No code was changed during this phase. Every external-endpoint
claim below was verified with a live request on 2026-08-10; raw results are in
§6. Nothing in this document is inferred from comments or docs — where the code
and the docs disagree, the code (and the wire) wins, and the disagreement is
recorded.

---

## 1. What this project actually is

Drift is a **PyQt5 desktop application** (Windows-first) that:

1. takes a resume file (PDF/DOC/DOCX),
2. extracts skills + a location + search keywords from it,
3. fans out across up to 12 job sources concurrently,
4. scores each listing against the resume with a local keyword algorithm,
   optionally refined by a Groq-hosted LLM for the top N,
5. shows ranked cards with save/apply/dismiss state persisted in SQLite,
6. exports CSV / JSON / HTML and drafts cover letters.

It is **not** a web app, has **no server**, and has **no build step**. This
materially affects the target spec: Phase 1's design system, Phase 10's
dashboard, and the `/design-system` route all presuppose a web front-end that
does not exist here. See §9.1 — this is the single biggest decision to make
before Phase 1, and it is a decision for you, not for me.

**Size:** 4,921 lines of Python across 37 files (46 tracked files total).

| Package | Files | Lines | Responsibility |
|---|---:|---:|---|
| `ui/` | 9 | 1,811 | PyQt5 screens, widgets, worker thread, style tokens |
| `core/scraper/` | 16 | 1,439 | One module per job source + shared helpers |
| `core/` (rest) | 9 | 1,444 | Resume parsing, scoring, AI client, config, export |
| `db/` | 1 | 148 | SQLite persistence |
| root | 2 | 79 | Entry point + dataclasses |

---

## 2. Annotated file tree

```
Drift/
├── main.py                     Entry point. Loads .env, boots QApplication, shows DriftApp.
├── models.py                   Job dataclass + job_fingerprint() + 4 status constants.
├── requirements.txt            13 deps, ALL unpinned (>= only). No lockfile.
├── .env                        LOCAL ONLY — gitignored, never committed (verified §7.1).
├── .env.example                Template: GROQ_API_KEY, GROQ_MODEL, MAX_JOBS_TO_SCORE.
├── README.md / CHANGELOG.md / TODO.md   Docs. CHANGELOG is accurate; TODO is stale.
│
├── core/
│   ├── config.py               .env read/write. Groq key/model/budget getters. GROQ_MODELS tuple.
│   ├── parser.py               Resume text extraction. PDF (3-way fallback), DOCX, DOC (3-way).
│   ├── local_engine.py         ★ Offline scoring: skill extraction, relevance filter, analyze().
│   ├── skills_db.py            190-entry hardcoded skill vocabulary + soft-skill exclusion set.
│   ├── ai_engine.py            Groq client (via openai SDK). Batch rerank, resume parse, cover letter.
│   ├── matcher.py              ★ Orchestrates local score → LLM refine → merge → Job objects.
│   ├── report.py               CSV / JSON / HTML export. Jinja2 with an inline fallback renderer.
│   ├── url_utils.py            Validates custom "company.com/jobs" URLs. Rejects anything deeper.
│   └── scraper/
│       ├── base.py             RawJob dataclass + BaseScraper ABC.
│       ├── util.py             strip_html, human_date, money, keyword_match.
│       ├── __init__.py         SCRAPERS registry + SOURCES UI catalog + alias resolution.
│       ├── jobicy.py           ✅ JSON API. Tag-mapped server-side filter.
│       ├── themuse.py          ✅ JSON API. Category-mapped, 2 pages.
│       ├── arbeitnow.py        ✅ JSON API. Cursor-paginated, 3 pages.
│       ├── remoteok.py         ✅ JSON API. Full feed, client-side keyword filter.
│       ├── remotive.py         ✅ JSON API. Server-side search param.
│       ├── hn.py               ✅ HN Algolia API. Mines "Who is hiring" comments with regex.
│       ├── wwr.py              ✅ HTML scrape. robots-allowed.
│       ├── ziprecruiter.py     ⛔ HTML scrape. robots DISALLOWED + live 403.
│       ├── internet_google.py  ⛔ HTML scrape of google.com/search. robots DISALLOWED.
│       ├── internet_bing.py    ⛔ HTML scrape of bing.com/search. robots DISALLOWED.
│       ├── linkedin.py         ⛔ undetected-chromedriver. robots DISALLOWED + evasion flags.
│       ├── indeed.py           ⛔ undetected-chromedriver. Live 403 + evasion flags.
│       └── custom.py           User-supplied /jobs page. JSON-LD → containers → li → links.
│
├── db/__init__.py              SQLite. jobs table + legacy seen_jobs. No migrations, no WAL, no FTS.
├── ui/
│   ├── app.py                  QMainWindow + QStackedWidget (3 screens) + worker wiring.
│   ├── worker.py               ★ ScanWorker(QThread). ThreadPoolExecutor(max 4) over sources.
│   ├── screen_setup.py         Resume drop zone, custom URL, source grid, threshold slider.
│   ├── screen_scan.py          Progress bar + 6 fixed log lines matched by SUBSTRING (fragile).
│   ├── screen_results.py       Job cards, live threshold/search/status filters, export menu.
│   ├── dialogs.py              SettingsDialog (Groq key) + CoverLetterDialog + local fallback.
│   ├── widgets.py              TopBar, SourceCheckbox, ThinProgressBar, LogLine, chip().
│   └── styles.py               ~30 hardcoded hex constants + one giant f-string Qt stylesheet.
├── templates/report.html       Jinja2 HTML report template.
└── assets/fonts/.gitkeep       Empty. No bundled fonts.
```

★ = highest-churn / highest-risk modules. ✅/⛔ = live-verified status, §6.

---

## 3. Stack inventory

| Concern | Current state |
|---|---|
| Language | Python 3.14.4 (venv at `.venv/`) |
| UI framework | PyQt5 ≥5.15 (desktop, Qt Widgets — **not** QML, **not** web) |
| Package manager | pip + `requirements.txt`. **No lockfile, no pinned versions, no `pyproject.toml`** |
| Build tool | None. Runs from source via `python main.py` |
| Styling | `ui/styles.py` — Python constants injected into a Qt Style Sheet f-string |
| State management | Ad-hoc. Widget instance attributes + signals. No store |
| Database | SQLite via stdlib `sqlite3`. One table + one legacy table. **No ORM, no migrations** |
| Test runner | **None.** Zero test files, zero fixtures, zero CI |
| CI | **None.** No `.github/`, no pre-commit, no secret scanning, no dependency audit |
| Concurrency | `QThread` for the scan + `ThreadPoolExecutor(max_workers=min(n,4))` for sources |
| LLM access | `openai` SDK pointed at Groq's OpenAI-compatible endpoint |
| Packaging | None. No installer, no entry point script, no icon |

**Dependency risk:** all 13 dependencies are floating (`>=`). A `pymupdf` or
`openai` major release can break the app with no code change and no way to
reproduce a working set. `undetected-chromedriver` is additionally a
maintenance liability — see §7.3.

---

## 4. Current data model

### 4.1 In-memory

**`RawJob`** (`core/scraper/base.py`) — what a scraper returns.
`title, company, location, description, url, source, job_type, salary, posted,
remote, rich`. Derived `id` property → `job_fingerprint(url, title, company)`.

**`Job`** (`models.py`) — what the scorer returns and the UI renders.
All `RawJob` display fields plus `matched_skills[], missing_skills[], score,
summary, verdict, status, is_new, cover_letter, scraped_at`.

**`job_fingerprint(url, title, company)`** — `sha1(...)[:16]` of the
lowercased, trailing-slash-stripped **URL**, falling back to `title::company`
only when the URL is empty.

> ⚠️ **This is the single most consequential design flaw for the target spec.**
> Fingerprinting on URL means the *same job on 15 boards produces 15 distinct
> records*. Cross-source deduplication — Phase 8's core requirement — is
> currently **impossible**, not merely absent. `dedupe_by_url()` removes exact
> URL repeats within one scan and nothing more. Every list the user sees today
> may contain the same role many times over.

### 4.2 Persisted (`db/jobs.db`)

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY, url TEXT, title TEXT, company TEXT,
  location TEXT, source TEXT, score INTEGER DEFAULT 0,
  status TEXT DEFAULT 'new', cover_letter TEXT DEFAULT '',
  first_seen TEXT, last_seen TEXT
);
CREATE TABLE seen_jobs (            -- legacy 1.x, written by nothing, read by nothing
  url TEXT PRIMARY KEY, title TEXT, company TEXT, source TEXT, scraped_at TEXT
);
```

**Everything the target spec needs is missing.** There is no `profile`,
`resume`, `resume_version`, `search`, `run`, `source`, `run_source_result`,
`job_score`, `application`, `blocklist`, `api_key`, or `setting` table. There
are **no indexes** beyond the implicit primary keys, **no FTS5**, **no WAL
mode**, and **no migration mechanism** — schema changes happen via
`CREATE TABLE IF NOT EXISTS` only, so no column has ever been altered and none
can be without hand-written code.

`status` is stored as a free-text string with no CHECK constraint.
`first_seen`/`last_seen` are `datetime('now')` strings (UTC, no timezone marker).

**Data-integrity defect:** `set_status()` and `save_cover_letter()` both
`INSERT ... ON CONFLICT DO UPDATE` supplying only `job_id` + one column. If
either is called for a `job_id` not yet in the table, it creates a **row with
NULL title, company, and url** — an orphan that `known_ids()` will then count
as a previously-seen job forever.

---

## 5. Current resume-scoring pipeline

**Entry point:** `ui/worker.py::ScanWorker.run()` (a `QThread`).

```
resume file
  └─> core.parser.extract(path)                    [PDF: pdfplumber → pymupdf → pypdf
      │                                             DOCX: python-docx
      │                                             DOC: win32com → LibreOffice → antiword]
      └─> raises if < 20 chars extracted. NO OCR PATH AT ALL.
  └─> ScanWorker._parse(text)
      ├─ if Groq key set: ai_engine.parse_resume()  → {skills, location, keywords}
      └─ on ANY exception, or no key: local_engine.parse_resume()
  └─> ScanWorker._scrape(keywords, location)       [ThreadPoolExecutor, max 4 workers]
  └─> db.dedupe_by_url()  →  drop db.dismissed_ids()
  └─> core.matcher.score_all(...)
      ├─ 1. local_engine.role_terms(keywords, skills)
      ├─ 2. dedupe by RawJob.id (fingerprint)
      ├─ 3. local_engine.is_relevant() filter — drops off-target listings
      │     (if it drops EVERYTHING, the filter is discarded and all jobs kept)
      ├─ 4. local_engine.analyze() on every survivor  → 0–100 baseline
      ├─ 5. sort desc, take top MAX_JOBS_TO_SCORE (default 15)
      ├─ 6. ai_engine.score_jobs_batch() — ONE call for all 15
      ├─ 7. _align() — trusts LLM ids only if they form a valid permutation
      └─ 8. _merge() — blend, then re-sort
  └─> annotate is_new / status, db.record_seen(), emit to ResultsScreen
```

### 5.1 The local algorithm (`local_engine.analyze`)

```
match_strength  = min(1.0, n_matched_skills / 5)
coverage        = n_matched / max(min(n_job_skills, 6), 1)
role_relevance  = 1.0  if ≥2 title hits
                  0.75 if  1 title hit
                  0.5  if the title contains any generic role word
                  0.0  otherwise
score = round(100 * (0.40*match_strength + 0.25*coverage + 0.35*role_relevance))
```

Matching uses a token-aware boundary regex where `+ # .` count as word
characters (so `c` will not match inside `c++`), and a `_PROSE` map forces
case-sensitive matching for ambiguous one/two-letter skills (`Go`, `R`, `C`,
`REST`) so the language "Go" never matches the verb "go". **This part is
genuinely well built** and should be preserved through the rewrite.

**What it cannot do**, all of which Phase 4 requires: years of experience,
seniority alignment, education/certification requirements, salary-band overlap,
location/work-mode compatibility, and every ATS mechanical check. The rubric has
three inputs; the target rubric has eight.

### 5.2 The LLM call

- **Where:** `core/ai_engine.py::score_jobs_batch()` — the only reranking call.
- **Provider:** Groq only, hardcoded `base_url="https://api.groq.com/openai/v1"`.
- **Prompt:** an inline f-string with a 5-band rubric (85-100 / 65-84 / 40-64 /
  15-39 / 0-14), sending `resume_text[:1500]`, `skills[:20]`, and up to 15
  listings truncated to `description[:1200]`.
- **Batching:** already correct — N jobs per call, not one call per job.
- **Structured output:** **none.** No JSON schema, no `response_format`. It asks
  politely for JSON, strips ``` fences, and `json.loads()`. On
  `JSONDecodeError` it returns `[]` and the run **silently** falls back to local
  scores. There is no repair retry.
- **Retry:** 4 attempts, but only for errors whose *stringified message*
  contains `"429"`, `"rate"`, or `"quota"`. Backoff 3→6→12→24s capped at 45.
  **`Retry-After` is not read.** Jitter is absent. Any other error re-raises
  immediately.

### 5.3 The merge (`matcher._merge`)

```
if ai_score >= local:  final = 0.7*ai + 0.3*local          (LLM may lift freely)
else:                  final = max(0.5*ai + 0.5*local, local - 20)   (bounded drop)
verdict = _verdict(final)   -- always re-derived, so score/verdict never disagree
```

Deliberate and defensible. **But it is not explainable in the Phase 8 sense:**
the UI shows one blended number with no sub-score breakdown, and there is no
record of which model produced it. The spec's rule — *"if you cannot show why,
do not show the number"* — is currently violated on every card.

---

## 6. All external calls — live-verified 2026-08-10

Every row below was probed with a real GET using the exact URL, params, and
User-Agent the shipped code sends. `robots` is the verdict from
`urllib.robotparser` against that same UA, cross-checked against the verbatim
`robots.txt` directives quoted underneath.

| # | Source | Endpoint | Auth | HTTP | Latency | Payload | robots.txt |
|---|---|---|---|---:|---:|---|---|
| 1 | Jobicy | `jobicy.com/api/v2/remote-jobs` | none | 200 | 2.1s | 5 jobs | fetch 403 (undeterminable) |
| 2 | The Muse | `themuse.com/api/public/jobs` | none | 200 | 1.5s | 20 results | **allowed** |
| 3 | Arbeitnow | `arbeitnow.com/api/job-board-api` | none | 200 | 1.1s | 176 items | **allowed** |
| 4 | RemoteOK | `remoteok.com/api` | none | 200 | **15.9s** | 101 items | **allowed** |
| 5 | Remotive | `remotive.com/api/remote-jobs` | none | 200 | 1.5s | 20 jobs | fetch 403 (undeterminable) |
| 6 | HN Algolia | `hn.algolia.com/api/v1/*` | none | 200 | 1.7s | 6 hits | 404 (no robots.txt) |
| 7 | We Work Remotely | `weworkremotely.com/remote-jobs/search` | none | 200 | 1.2s | 145 KB HTML | **allowed** |
| 8 | ZipRecruiter | `ziprecruiter.com/jobs` | none | **403** | 0.8s | — | **DISALLOWED** |
| 9 | Google | `google.com/search` | none | 200 | **85.9s** | 92 KB HTML | **DISALLOWED** |
| 10 | Bing | `bing.com/search` | none | 200 | 2.6s | 118 KB HTML | **DISALLOWED** |
| 11 | LinkedIn | `linkedin.com/jobs/search/` | none | 200 | 2.1s | 273 KB HTML | **DISALLOWED** |
| 12 | Indeed | `indeed.com/jobs` | none | **403** | 0.8s | — | allowed (path), blocked in practice |
| — | Groq | `api.groq.com/openai/v1` | `GROQ_API_KEY` | not probed (would spend user quota) | | | n/a |

### 6.1 Verbatim robots.txt directives for the five blocked sources

```
ziprecruiter.com   User-agent: *  →  Disallow: /
                   also explicit: Disallow: /jobs/ , Disallow: /jobs-search
google.com         User-agent: *  →  Disallow: /search
bing.com           User-agent: *  →  Disallow: /search
linkedin.com       User-agent: *  →  Disallow: /
                   "If you would like to crawl LinkedIn, please email
                    whitelist-crawl@linkedin.com to apply for white listing."
                   also explicit: Disallow: /jobs-guest/
indeed.com         User-agent: *  →  Allow: /   (so /jobs?q= is NOT robots-blocked)
```

**Indeed is the nuanced case and deserves a precise statement.** Its
`robots.txt` does *not* forbid `/jobs?q=`. Indeed is disqualified for two
different reasons: it returns a hard **403** to the shipped request, and the
adapter reaches for it with `undetected-chromedriver` plus
`--disable-blink-features=AutomationControlled` — which is **detection evasion**,
prohibited outright by Prime Directive 4 and by the hard constraints. LinkedIn's
adapter carries the identical evasion flags *and* is robots-disallowed.

**Conclusion: 5 of the 12 shipped sources (42%) must be removed.** Sources 8–12
above cannot ship under this project's own compliance rules. Two of them
(#9 Google, #11 LinkedIn) currently return HTTP 200, so they *look* like they
work — nothing in the app or its docs tells the user their job search is
scraping endpoints that forbid it.

### 6.2 Other findings from the wire

- **RemoteOK 15.9s and Google 85.9s** are not outliers I can wave away — they
  are single-source stalls against the app's 30s `requests` timeout and its
  4-worker pool. Google alone can hold a scan open for a minute and a half.
- **RemoteOK's robots.txt** carries `Content-Signal: search=yes, ai-train=no,
  use=reference`. Drift's use is search/reference and it does not train models,
  so this is consistent — but it must be recorded and honoured in
  `docs/COMPLIANCE.md`, and it forbids any future "train on scraped listings"
  feature.
- **Remotive ignores `limit`** — asked for 5, returned 20. The adapter's
  `MAX_RESULTS=60` is therefore advisory, not enforced.
- **Jobicy and Remotive return 403 on `/robots.txt` itself.** Their crawl policy
  is undeterminable by machine. Both publish these as documented public APIs, so
  API access is intended; this should be resolved by reading their published
  terms during Phase 6 rather than assumed either way.

### 6.3 Where the API key lives

`GROQ_API_KEY` is read from `.env` in the repo root via `python-dotenv`, into
`os.environ`, cached in a module-global `OpenAI` client. Written back to `.env`
in **plaintext** by `config.save_settings()` from the Settings dialog.

Assessed honestly: `.env` is correctly gitignored and **has never been
committed** (§7.1), the input uses `QLineEdit.Password` echo mode, and the key
is never logged. That is better than average. But it is plaintext on disk, it is
readable by any process running as the user, and it is a **single-provider**
design — Phase 3 needs OS-keychain storage and eight providers.

---

## 7. Code quality findings

### 7.1 Secrets — clean ✅

- `git log --all -- .env` → **empty. The file has never been committed.**
- Regex sweep for `sk-`, `gsk_`, `AIza`, `xox[baprs]-`, PEM headers across all
  tracked files → **no matches**.
- Same sweep across **all history** (`git log --all -p`) → **no matches**.
- No secret scanning in CI, because there is no CI. Phase 3 must add one.

### 7.2 Dead code — confirmed by reference count, not by eye

| Symbol | Location | External refs |
|---|---|---:|
| `mark_jobs_seen()` | `db/__init__.py` | **0** |
| `seen_jobs` table | `db/__init__.py` | **0** (created, never read or written) |
| `ALL_STATUSES` | `models.py` | **0** |
| `LOG_KEYS` | `ui/screen_scan.py` | **0** |
| `InvalidRootUrlError`, `normalize_root_url()` | `core/url_utils.py` | **0** |
| `local_engine.score_job/score_jobs_batch` | `core/local_engine.py` | **0** |
| `ai_engine.extract_skills/extract_location/generate_keywords` | `core/ai_engine.py` | **0** |
| `ai_engine.score_job()` | `core/ai_engine.py` | 0 real (wraps the batch fn) |
| `_REMOTE_RE` | `core/local_engine.py` | **0** (defined, never used) |
| `SOURCE_KEYS` | `ui/worker.py` | legacy label→key map; setup screen now emits keys |
| `BaseScraper.label/needs_browser/recommended` | `core/scraper/base.py` | UI reads the `SOURCES` dict instead |

**`RawJob.rich` is a live bug, not just dead weight.** Six scrapers set
`rich=True`; the field's own docstring says it is *"used by the matcher to
decide whether LLM scoring is worthwhile."* **`matcher.py` never reads `.rich`.**
So title-only listings from HTML sources are sent to the LLM as if they had full
descriptions, wasting tokens and producing scores from a bare job title.

### 7.3 Compliance and safety defects

1. **Detection evasion shipped in two adapters.** `linkedin.py` and `indeed.py`
   both use `undetected-chromedriver` with
   `--disable-blink-features=AutomationControlled`. Prohibited. Remove.
2. **Dishonest User-Agent in five adapters.** `remoteok`, `arbeitnow`, `jobicy`,
   `custom`, and the browser adapters all send a spoofed
   `Mozilla/5.0 ... Chrome/120.0` string. The spec requires *"a real, current,
   honest user-agent."* Notably `wwr.py` already does the right thing
   (`drift.jobs/1.0`) — and is robots-allowed under it.
3. **No robots.txt check anywhere in the codebase.** Not one adapter fetches it.
   The `custom.py` scraper will fetch *any* user-supplied `/jobs` URL with zero
   policy check.
4. **No rate limiting of any kind.** No token bucket, no per-domain concurrency
   cap, no delay between requests. `custom.py` and `ziprecruiter.py` loop pages
   with only a bare `time.sleep(1)` in the latter.

### 7.4 Silent failure — pervasive, and directly against Prime Directive 3

Every one of these swallows an exception and returns an empty list, so a dead
source is indistinguishable from a source that legitimately found nothing:

`remoteok.py:31`, `remotive.py:26`, `arbeitnow.py:38`, `jobicy.py:76`,
`themuse.py:60`, `hn.py:47` and `:63`, `custom.py:_fetch`,
`internet_google.py:52`, `internet_bing.py:48`, `ziprecruiter.py:66`.

`ui/worker.py` does slightly better — it logs `"{key} — failed ({ExceptionType})"`
— but **no HTTP status, no error detail, and no timestamp** ever reaches the
user. The spec requires all three.

`ai_engine.score_jobs_batch()` returning `[]` on a JSON parse failure is the
worst of these: the user sees local-only scores and is never told the AI step
silently did nothing.

### 7.5 Correctness defects

1. **`ui/screen_setup.py::_set_upload_idle()`** calls
   `QVBoxLayout(self.upload_zone)` on a widget that may already own a layout.
   `_set_upload_done()` guards this with the `QWidget().setLayout(...)` reparent
   trick; `_set_upload_idle()` does not. Upload a good resume, then a bad one →
   Qt emits *"Attempting to add QLayout to QPushButton which already has a
   layout"* and the drop zone renders wrong.
2. **`ui/screen_scan.py::update_log()` routes log lines by substring match**,
   including a bare `"—" in message` test. Any source whose name or error text
   contains an em-dash lands in the wrong row. This is why the scan log
   misbehaves with multiple failing sources.
3. **Orphan DB rows** from `set_status`/`save_cover_letter` — see §4.2.
4. **`skills_db.SKILLS` contains `"rabbitmq"` twice** (190 entries, 189 unique).
   Harmless today because lookups dedupe by lowercase key, but it inflates the
   iteration in `analyze()` and signals the list is unmaintained.
5. **`recommended` metadata contradicts itself.** `RemoteOKScraper.recommended`
   and `RemotiveScraper.recommended` are both `True` on the class, but the
   `SOURCES` catalog the UI actually reads says `False` for both. Two sources of
   truth, already out of sync.
6. **`matcher.score_all` keeps every job when the relevance filter rejects all
   of them** (`# else: nothing looked relevant — keep everything`). Defensible as
   a "never show an empty screen" choice, but it means a resume that matches
   nothing yields a full page of confidently-scored irrelevant jobs.

### 7.6 Hardcoded values

- **~30 hex colors** in `ui/styles.py`, plus more inline in `report.py`'s
  fallback renderer and `templates/report.html`. Phase 1 forbids any hex outside
  a token file.
- **Font stack** `'"Segoe UI", "Inter", system-ui, sans-serif'` — no Apple
  system fonts, and `assets/fonts/` is empty despite Phase 1 requiring bundled
  Inter.
- **All font sizes, paddings, and radii are inline literals** in per-widget
  stylesheet strings across all 9 UI files. There is no spacing scale and no type
  scale.
- **Every LLM prompt is an inline f-string** in `ai_engine.py` — not versioned,
  not testable, not swappable.
- **`GROQ_MODELS`** is a hardcoded 4-model tuple in `config.py` with no
  `lastVerified` date and no `/models` fetch. Phase 3 forbids exactly this.
- Skill→tag maps (`jobicy._TAG_MAP`, `themuse._CATEGORY_MAP`) and the 18-city
  list in `local_engine._CITIES` are hardcoded and English/tech-centric.

### 7.7 Duplicated logic

- `parse_resume`, `extract_skills`, `extract_location`, `generate_keywords`,
  `score_job`, `score_jobs_batch` all exist in **both** `ai_engine` and
  `local_engine` with the same names and different semantics. Only
  `parse_resume` and `score_jobs_batch` are genuinely dual-implemented by design;
  the rest are dead duplicates (§7.2).
- `_verdict()` lives in `local_engine` but is called from `matcher` via the
  private name `local_engine._verdict` — a private symbol used across modules.
- Two HTML renderers in `report.py` (`templates/report.html` via Jinja2, plus a
  full inline `_render_fallback`) that must be kept visually in sync by hand.
- The `Mozilla/5.0 ... Chrome/120.0` UA string is copy-pasted into 4 files.

### 7.8 Test coverage

**Zero.** No test files, no `conftest.py`, no fixtures, no CI, no coverage
config. Every number in Phase 11 starts from nothing.

This is the highest-risk finding in the audit. The scoring math, the
fingerprinting, the `_align` permutation guard, and the `_merge` blending are all
subtle, all load-bearing, and all completely unverified. **The migration plan
below therefore front-loads a characterization test suite over the existing
behaviour — before anything is rewritten.**

---

## 8. Where the docs disagree with the code

| Claim | Reality |
|---|---|
| `README`/`SOURCES` call RemoteOK "broad feed", not recommended | class says `recommended = True` (§7.5) |
| `RawJob.rich` docstring: "used by the matcher" | never read (§7.2) |
| `TODO.md`: "Full JD fetch for LinkedIn/Indeed" | both adapters must be deleted (§6) |
| `SOURCES` notes: Google/Bing "best-effort link discovery" | both robots-disallowed (§6.1) |
| `CHANGELOG` 2.0 | accurate — matches the code well |

---

## 9. Migration plan

Ordered by dependency. The spec's execution order is
**0 → 2 → 3 → 1 → 6(T1) → 7 → 8 → 5 → 4 → 6(T2-6) → 9 → 10 → 11**, which I
agree with and have kept. Two insertions are marked ⚠️ where I believe the spec's
order carries avoidable risk.

### 9.1 ⚠️ BLOCKING DECISION — the UI platform

Phase 1 specifies backdrop-filter materials, a `/design-system` **route**, `⌘K`
command palette, WCAG contrast audits, and `prefers-reduced-motion`. Phase 10
specifies a virtualised 5,000-row table. **Qt Style Sheets support none of this
natively** — there is no backdrop-filter, no routing, and no virtualised table
widget of that class.

Three honest options:

| Option | Effort | Consequence |
|---|---|---|
| **A. Port to web** (Tauri/Electron + React, or FastAPI + browser) | Highest — all 1,811 UI lines rewritten | Every Phase 1/10 requirement becomes achievable as written. Python core (`core/`, `db/`) survives intact behind an API |
| **B. Stay PyQt5, adapt the spec** | Lowest | Keeps working software. Must formally drop backdrop blur, the `/design-system` route, and `⌘K`; approximate the rest with QSS + `QAbstractItemModel` |
| **C. PyQt5 → QML/Qt Quick** | High | Real animation and GPU compositing; still no CSS backdrop-filter, still no web routing. Worst effort-to-payoff ratio of the three |

**My recommendation: A.** Phases 2 and 3 are pure Python and are unaffected
either way, so the port can happen at the Phase 1 boundary without stalling
anything. Choosing B is entirely reasonable if you want a desktop app — but it
must be a stated decision that rewrites Phase 1's deliverables, not a silent
shortfall discovered at Phase 10.

**This is the one thing I need from you before Phase 1.** Phase 2 and Phase 3
can begin immediately regardless.

### 9.2 ⚠️ Inserted step — characterization tests (before Phase 2)

The spec puts all testing in Phase 11. With zero tests today and a rewrite of
the fingerprinting and scoring ahead, that ordering means rewriting unverified
behaviour with nothing to compare against. I propose a small pre-Phase-2 step:
pin the current behaviour of `local_engine.analyze`, `job_fingerprint`,
`matcher._align`, `matcher._merge`, and `util.human_date/money/strip_html` with
golden tests. ~200 lines, and it makes every later phase safe. Phase 11 remains
as specified.

### 9.3 Ordered plan

| # | Phase | Work | Risk |
|---|---|---|---|
| 0 | — | This audit | none |
| 1 | ⚠️ pre-2 | Characterization tests over current scoring/fingerprint/format helpers | none |
| 2 | **P2** | New SQLite schema, WAL, FTS5, migration framework. **13 new tables.** | 🔴 **Destructive.** See §9.4 |
| 3 | **P3** | Provider abstraction; port Groq→adapter; add 7 providers; keychain storage; task routing; cost meter | 🟠 `GROQ_API_KEY` must migrate out of `.env` into the keychain without stranding the user's existing key |
| 4 | **DECISION** | §9.1 resolved | — |
| 5 | **P1** | Design system + tokens + component library | 🟠 Total UI rewrite under option A |
| 6 | **P6-T1** | Delete 5 non-compliant adapters. Declarative source definitions. robots checker. Honest UA. Tier-1 ATS (Greenhouse/Lever/Ashby/Workable/SmartRecruiters) | 🟠 **User-visible capability loss** — see §9.5 |
| 7 | **P7** | Worker pool, token-bucket limiter, circuit breaker, checkpointing, cancellation | 🟡 Replaces `ScanWorker` wholesale |
| 8 | **P8** | Content-based fingerprint + simhash + clustering. Normalization. 3-stage ranking | 🔴 **Fingerprint change invalidates every stored `job_id`** — see §9.4 |
| 9 | **P5** | Search criteria builder + saved searches | 🟢 |
| 10 | **P4** | Resume module: multi-resume, structured extraction, 8-dimension rubric, tailoring, ATS checks | 🟠 Must keep local scoring working throughout |
| 11 | **P6-T2..6** | Remaining source tiers, each with a live verification test | 🟡 Rejected sources → `SOURCES_REJECTED.md` |
| 12 | **P9** | Application tracker (Kanban) | 🟢 |
| 13 | **P10** | Dashboard + settings | 🟢 |
| 14 | **P11** | Full quality gates, CI, a11y audit, perf budgets | 🟢 |

### 9.4 🔴 Destructive changes — both need reversible migrations

**(a) Schema replacement (Phase 2).** The existing `jobs` table holds the only
thing in this app that is genuinely irreplaceable: **the user's save/apply/dismiss
history and their saved cover letters.** Everything else can be re-scraped.

> **Required:** migration `001` copies every `jobs` row into the new `job` +
> `application` tables *before* any drop, keyed by the old `job_id`; back up
> `db/jobs.db` to `db/jobs.db.bak-<ts>` first; provide a down-migration. The
> legacy `seen_jobs` table is provably unused (§7.2) and can be dropped without
> preserving anything.

**(b) Fingerprint change (Phase 8).** Moving from URL-hash to
`company+title+city+simhash(description)` means **every existing `job_id` stops
matching**. Done naively, every dismissed job resurfaces and every saved job
detaches from its listing — the exact failure the user would notice first.

> **Required:** migration `00N` recomputes the new fingerprint for every stored
> row from its retained `url/title/company/location`, and writes an
> `alias(old_job_id → new_fingerprint)` table so history survives. Rows lacking
> enough data to recompute keep their old id and are flagged `legacy=1` rather
> than being silently dropped.

### 9.5 User-visible capability loss at Phase 6

Deleting LinkedIn, Indeed, ZipRecruiter, Google, and Bing removes 5 of 12
sources — including the two largest-brand names in the list. The user must be
told plainly, in `SOURCES_REJECTED.md` and in the app, *why* each one went and
what replaced it.

The replacement is genuinely better, and worth stating: **Tier-1 ATS adapters
(Greenhouse, Lever, Ashby, Workable, SmartRecruiters) are public, documented,
key-free JSON APIs that return the employer's own canonical posting.** That is
strictly higher-quality data than a scraped LinkedIn card — which, per §7.2,
currently arrives with **no description at all**, just a title. Net, this trades
5 non-compliant sources for a larger set of compliant ones with better data. But
it is a real change to what the user sees, and it should not be buried.

---

## 10. What carries forward vs. what gets replaced

**Keep — this code is good and should survive the rewrite:**
- `local_engine`'s token-aware boundary matching and the `_PROSE` case-sensitivity
  trick (§5.1). It solves a real problem correctly.
- `matcher._align`'s permutation guard against LLM id renumbering.
- `matcher._merge`'s asymmetric blending rationale.
- `parser.py`'s layered PDF/DOC extraction fallbacks.
- `url_utils`' strict validation posture.
- Batch reranking (already N-per-call, as Phase 3 requires).

**Replace wholesale:** `job_fingerprint`, `db/__init__.py`, `ui/styles.py`,
`ScanWorker`, all 5 non-compliant adapters, and `ai_engine`'s single-provider
client.

---

## 11. Phase 0 status

**Audit complete. No code changed. Awaiting confirmation to begin Phase 1**
(which, per the spec's execution order, means Phase 2 — the data layer).

**One blocking question:** §9.1 — PyQt5 or web?
**One proposed deviation:** §9.2 — characterization tests before Phase 2.

**What I could not verify:**
- Jobicy's and Remotive's crawl policy — both return 403 on `/robots.txt`
  itself. Their published API terms must be read by a human before Phase 6.
- The Groq API — not probed, because a live call spends the user's quota. The
  key is present in `.env` and the integration code is sound on inspection.
- Runtime behaviour of the PyQt5 UI — this environment has no display, so every
  UI defect in §7.5 is from code reading, not from running the app.
