# Sources — shipped

Every source Drift ships, its auth model, and the date its endpoint was last
verified live. Tier-1 sources are **declarative** (`core/sources/definitions/`);
the legacy feeds are first-party scrapers (`core/scraper/`). All are key-free and
robots-respecting. See `docs/SOURCES_REJECTED.md` for what was removed and why,
and `docs/COMPLIANCE.md` for the policy.

## Tier 1 — ATS (employer-canonical, declarative)

These query a company's own applicant-tracking-system board, so the data is the
employer's canonical posting — higher fidelity than any aggregator or scraped
card. Each queries a curated seed list of company boards
(`core/sources/seeds.py`, all verified 2026-08-10); users can extend it.

| Source | Endpoint | Auth | robots | Descriptions | Verified |
|---|---|---|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{co}/jobs?content=true` | none | allowed | full HTML | 2026-08-10 |
| Lever | `api.lever.co/v0/postings/{co}?mode=json` | none | allowed | full plain | 2026-08-10 |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{co}` | none | none served (allowed) | full HTML + comp | 2026-08-10 |
| Workable | `apply.workable.com/api/v1/widget/accounts/{co}?details=true` | none | allowed | full HTML | 2026-08-10 |

Seed boards (verified returning real jobs on 2026-08-10):
- **Greenhouse:** stripe, airbnb, gitlab, coinbase, robinhood, dropbox, figma, databricks
- **Lever:** spotify, matchgroup, gopuff, ro
- **Ashby:** ashby, linear, posthog, hex, ramp, runway
- **Workable:** huggingface

Rate limits are self-imposed (120 rpm/host, concurrency 4); these APIs publish no
hard public quota. Each source has a circuit breaker (5 consecutive failures →
1-hour cool-off → half-open probe) with health persisted to the `source` table.

## Tier 2 — aggregators (declarative, public APIs)

Key-free remote-job APIs verified live 2026-08-10, robots-allowed for our UA.

| Source | Endpoint | Auth | Descriptions | Verified |
|---|---|---|---|---|
| Himalayas | `himalayas.app/jobs/api?limit=N` | none | full + salary + seniority | 2026-08-10 |
| Working Nomads | `workingnomads.com/api/exposed_jobs/` | none | full HTML + direct apply URL | 2026-08-10 |

## Tier 6 — browser adapter (framework)

A compliance-first Playwright adapter (`core/sources/browser.py`) for sites with
no API. **Not shipped enabled** — Playwright is not a Drift dependency, so it
degrades to `skipped` until a user installs it and defines a `BrowserSource`. Its
guardrails are built and unit-tested: robots check before every browse, human
pacing (randomized 2–6s, one session per domain, hourly cap), a persistent
per-site profile (the user logs into their OWN account in a visible window — the
app never handles the password), an honest user-agent, and — on any 403 / 429 /
CAPTCHA — it stops, marks the source `blocked`, backs off, and routes to a search
fallback. It never solves or evades a challenge. Screenshot + DOM snapshot are
written to `logs/failures/` on any failure.

## Tier 5 — community (bring-your-own-credential)

These are legitimate but require the user's own token/app, so they are documented
rather than shipped with credentials baked in:

- **Reddit** (r/forhire, r/remotejs, hiring threads) — the official OAuth API with
  a user-registered app. Free, rate-limited, legitimate. Never scrape old.reddit.
- **Hacker News** "Who is hiring" — already shipped (Algolia API, no key).
- **Discord / Slack / Telegram** job channels — via a token the user provides.
- **X/Twitter** search — where the user holds API access.
- **GitHub jobs-repos** (`awesome-jobs`-style) — public repo parsing.

Wiring each requires the user's credential in Settings; adding one is the same
declarative-definition step as any other source.

## Legacy feeds (first-party, key-free)

| Source | Endpoint | Auth | robots | Verified |
|---|---|---|---|---|
| Jobicy | `jobicy.com/api/v2/remote-jobs` | none | 403 on robots.txt* | 2026-08-10 |
| The Muse | `themuse.com/api/public/jobs` | none | allowed | 2026-08-10 |
| Arbeitnow | `arbeitnow.com/api/job-board-api` | none | allowed | 2026-08-10 |
| RemoteOK | `remoteok.com/api` | none | allowed | 2026-08-10 |
| Remotive | `remotive.com/api/remote-jobs` | none | 403 on robots.txt* | 2026-08-10 |
| Hacker News | `hn.algolia.com/api/v1/*` (Who is hiring) | none | no robots.txt | 2026-08-10 |
| We Work Remotely | `weworkremotely.com/remote-jobs/search` (HTML) | none | allowed | 2026-08-10 |
| Custom `/jobs` | user-supplied company page (JSON-LD → HTML) | none | checked per fetch | n/a |

\* Jobicy and Remotive return HTTP 403 on `/robots.txt` itself, so a machine
verdict is impossible; both publish these as documented public job APIs, so API
access is intended. Flagged in `docs/COMPLIANCE.md` for a human ToS read.

## Adding a source
Drop a module exposing `DEFINITION` into `core/sources/definitions/` and list it
in that package's `ALL`. No engine code changes. A live verification (real
request, real jobs) is required before it ships — the `DRIFT_LIVE=1` smoke test
enforces this per adapter.
