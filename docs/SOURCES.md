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
