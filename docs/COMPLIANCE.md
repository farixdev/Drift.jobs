# Compliance posture

What Drift does and does not do when fetching job data. This is both the legal
position and the engineering one — detection evasion breaks continuously and
isn't worth maintaining.

## robots.txt
- Declarative sources with `robots_check: true` (all Tier-1 ATS) verify our
  User-Agent is allowed **before every fetch** (`core/sources/robots.py`, cached
  per host). An explicit `Disallow` is respected: the fetch is skipped and the
  source is surfaced as `blocked` — never silently.
- A missing/unreadable `robots.txt` (404/401/network) is treated as *allowed* —
  absence of rules is not a prohibition.
- Sources found robots-disallowed are removed and logged in
  `docs/SOURCES_REJECTED.md` with the date tested.
- **Known gap:** Jobicy and Remotive return HTTP 403 on `/robots.txt` itself, so
  their crawl policy can't be determined by machine. Both are documented public
  job APIs; API access is intended. Action item: a human should read each API's
  published terms and record the outcome here. Until then they ship on the basis
  of being documented public APIs, and this gap is stated rather than hidden.

## User-Agent
One honest, identifiable UA on every request:
`drift-jobfinder/3.0 (+https://github.com/farixdev/Drift-JobFinder)`. Drift never
impersonates a browser or another client. (The remaining legacy feeds still send
a browser-like UA and will be migrated to the honest UA as they move to the
declarative system.)

## Rate limits
- Each source declares `rate_limit_rpm` and `concurrency_limit`; the runner bounds
  concurrency per source. A full token-bucket limiter per domain lands with the
  Phase 7 execution engine.
- **Circuit breaker** per source: 5 consecutive failures → disabled for 1 hour →
  a single half-open probe → success closes it. State persists to the `source`
  table so a struggling endpoint isn't hammered.

## Terms of service
- Tier-1 sources are the ATS platforms' **documented public job-board APIs**,
  intended for exactly this use (embedding a company's listings). No auth is
  bypassed; no paywall or login is circumvented.
- Drift only ever accesses accounts the user holds. It stores no scraped content
  for redistribution and does not train models on fetched listings. (RemoteOK's
  `robots.txt` carries `Content-Signal: ai-train=no, use=reference`; Drift's use
  is search/reference only, consistent with that signal.)

## What Drift will not do
- No CAPTCHA solving. No bot-detection bypass. No browser-fingerprint spoofing.
- No scraping of any site whose `robots.txt` disallows it.
- No paywall or login circumvention; no accessing accounts the user doesn't hold.
- On a 403/429/CAPTCHA challenge from any future browser-tier adapter: stop, mark
  the source `blocked`, back off, notify the user — never attempt to solve or
  evade.
- No storing, logging, or transmitting an API key anywhere but its own provider
  (see `docs/AI_PROVIDERS.md`).
