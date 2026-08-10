# Changelog

All notable changes to **Drift** are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-08-11

First public release. Drift is a local-first, privacy-respecting desktop app that
reads your résumé, finds matching jobs across many real sources, and explains
every score — no API key required to get started.

### Highlights
- **Résumé-driven search you can edit.** Upload a résumé (PDF/DOC/DOCX) or pick a
  **saved** one; Drift extracts your location and skills and shows them as
  editable fields/chips. Add your own skills, change the location — those drive
  both what's searched and how jobs are ranked.
- **See every match — scoring is optional.** Results default to showing *all*
  jobs matching your skills + location, sorted by score. The match-score slider
  is a soft filter, not a gate.
- **Explainable scores.** Every job shows a per-dimension breakdown (lexical /
  semantic / AI / freshness) and matched vs. missing skills — never a number you
  can't decompose.
- **Works offline, better with a key.** Local scoring out of the box; add a free
  Groq (or other provider) key in Settings for AI ranking, cover letters, and
  résumé tailoring. Keys are stored in the OS credential manager, never logged.

### Sources
- **Employer boards (ATS), key-free & robots-clean:** Greenhouse, Lever, Ashby,
  Workable, Recruitee — seeded with **60+ live-verified company boards**
  (thousands of postings) plus your own custom company boards.
- **Remote & aggregator feeds:** Himalayas, Working Nomads, Jobicy, The Muse,
  Arbeitnow, RemoteOK, Remotive, We Work Remotely, Hacker News "Who is hiring".
- **Custom job site:** point Drift at any `company.com/jobs` page.
- Every source is verified with a real request under an honest User-Agent and is
  robots.txt-checked before each fetch. Sources that require detection evasion or
  are robots-disallowed (LinkedIn, Indeed, ZipRecruiter, SmartRecruiters, …) are
  **not shipped** — see `docs/SOURCES_REJECTED.md`.

### Search & ranking
- Full, saveable **Search Builder** (titles, required/nice/excluded keywords,
  seniority, location mode, salary, employment type, company include/exclude,
  freshness, volume caps).
- Concurrent scan engine: bounded worker pool, per-domain rate limiting, retries
  with backoff, circuit breaker, checkpointing, live per-source progress, and
  cooperative cancellation.
- Content-fingerprint de-duplication clusters the same role posted to many boards
  into one card ("seen on N sites").
- Three-stage ranking (BM25 lexical → semantic embeddings → optional LLM rerank),
  blended with freshness.

### Résumé tools
- Structured extraction (LLM when a key is present, local parser otherwise) into
  an editable form; corrections persist. Multiple saved résumés with a default.
- Transparent rubric scoring, ATS checks, honest bullet tailoring (never invents
  employers, titles, dates, or metrics), gap reports, and PDF/DOCX/TXT export.

### Application tracking
- Kanban board (drag-and-drop stages), notes and next actions, funnel metrics,
  CSV/JSON export.

### Design & platform
- macOS/iOS-inspired design system: light/dark/auto themes, 8 accent colors,
  34 reusable components, DWM Mica backdrop, reduced-motion support.
- New **app icon and wordmark** (`assets/logo/`).
- Ships as a self-contained **Windows executable** (`Drift.exe`); the database
  and settings live in `%LOCALAPPDATA%\Drift`.

### Notes for this release
- Fixed résumé location detection mistaking skill lists ("Python, Django") for a
  location.
- Skills feed keyword matching with ANY-of semantics (a job matching even one of
  your skills appears) instead of requiring all of them.
- Text rendering cleaned up on Windows (removed macOS-style letter-spacing that
  caused overlapping glyphs); crisp Segoe Fluent icons throughout.

[1.0.0]: https://github.com/farixdev/Drift-JobFinder/releases/tag/v1.0.0
