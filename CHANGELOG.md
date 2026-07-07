# Changelog

## 2.0 — "the AI job co-pilot"

A ground-up upgrade of how Drift finds, scores, and helps you act on jobs.

### Added
- **Reliable, key-free job sources** — RemoteOK, Remotive, and Arbeitnow JSON
  APIs that return real job descriptions and don't get blocked. These are the
  new recommended defaults.
- **Hybrid scoring** — a free local baseline scores *every* job; Groq refines
  the top matches. Drift now works fully with **no API key**.
- **Gap analysis** — each job shows matched skills *and* the skills it wants
  that you're missing.
- **AI cover letter generator** — tailored, editable, copy/save, with tone
  options and a local-template fallback when no key is set.
- **Job states** — Save / Applied / Dismiss, persisted in SQLite. Dismissed
  jobs never resurface; previously-seen jobs are flagged **NEW**.
- **Live results filtering** — match-score slider, text search, and
  All/New/Saved/Applied filters, all without re-scanning.
- **In-app Settings dialog** — set Groq key, model, and scoring depth; writes
  back to `.env`. Reachable from every screen via the ⚙ top-bar button.
- **Parallel scraping** with an always-available **Stop** button.
- **Multi-format export** — CSV, JSON, and a polished HTML report.
- Richer job data end to end: salary, posted date, remote flag, verdict.

### Changed
- Scoring now uses **word-boundary matching** with token-aware handling of
  `c++`, `c#`, `.net`, and case-sensitive short skills (so the language "Go"
  no longer matches the verb "go").
- Scraping runs concurrently instead of sequentially.
- Verdict labels are always derived from the final score, so score and verdict
  never disagree.
- HTML report enriched with verdict, salary, posted date, and skill gaps.

### Fixed
- **Removed the broken pause/continue flow** — `maybe_pause()` emitted its
  prompt and then read the decision immediately without ever blocking, so it
  never worked. Replaced with a real, cancellable Stop.
- **Killed false-positive skill matches** — the old substring matcher counted
  skills like `r`, `go`, and `c` inside unrelated words.
- **Removed artificial score floors** (e.g. a flat +25 for any titled job) that
  defeated the match threshold.
- Docs corrected to reflect the real stack (Groq, not Gemini; CSV/JSON/HTML
  export) and current feature set.

### Migration notes
- No API key is needed to run. Existing `.env` files keep working; you can now
  edit settings from the app instead of by hand.
- The local database schema gained a `jobs` table for cross-scan state; it is
  created automatically on first run.
