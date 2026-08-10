# Sources — rejected

Sources that were removed or declined, with the reason and the date tested. Per
Prime Directive 2/4: a source that is robots-disallowed, gated, paid-only, or
requires detection-evasion does not ship.

## Removed in Phase 6 (were shipping in 1.x)

| Source | Tested | Reason |
|---|---|---|
| **LinkedIn** | 2026-08-10 | `robots.txt` `Disallow: /` for all UAs ("email whitelist-crawl@linkedin.com to apply"). The 1.x adapter also used `undetected-chromedriver` with `--disable-blink-features=AutomationControlled` — detection evasion. Removed on both grounds. |
| **Indeed** | 2026-08-10 | Returns HTTP 403 to the shipped request; the 1.x adapter used `undetected-chromedriver` + anti-automation flags — detection evasion. Removed. |
| **ZipRecruiter** | 2026-08-10 | `robots.txt` `Disallow: /` and explicit `Disallow: /jobs/`; live request returns HTTP 403. Removed. |
| **Google (web search scrape)** | 2026-08-10 | `robots.txt` `Disallow: /search`. Removed. |
| **Bing (web search scrape)** | 2026-08-10 | `robots.txt` `Disallow: /search`. Removed. |

The `selenium` and `undetected-chromedriver` dependencies were dropped with these
adapters.

## Evaluated for Phase 6 Tier 1, not shipped

| Source | Tested | Reason |
|---|---|---|
| **SmartRecruiters (Posting API)** | 2026-08-10 | The API host's `robots.txt` disallows our User-Agent on the postings path (`can_fetch=False` for `api.smartrecruiters.com/v1/companies/{co}/postings`). The endpoint is a documented public API and returns real data (Visa, Bosch verified), so the block is the crawler-vs-API-client nuance — but to stay consistent with how LinkedIn/Google were treated, it is not shipped as an automatic source. **Revisit** if SmartRecruiters clarifies that documented API use is exempt, or with explicit user authorization for their own company board. |

## Notes
- Jobicy and Remotive return HTTP 403 on `/robots.txt` itself (not on the API),
  so no machine verdict is possible. Both are documented public job APIs and
  continue to ship; a human ToS confirmation is tracked in `docs/COMPLIANCE.md`
  rather than treated as a silent pass.

## Evaluated for the 2026-08-11 source expansion, not shipped

| Source | Tested | Reason |
|---|---|---|
| **SmartRecruiters (Posting API)** | 2026-08-11 | Re-confirmed the Phase-6 verdict: `api.smartrecruiters.com/robots.txt` is `User-agent: * / Disallow: /` — only `LinkedInBot` is allowed on `/v1/companies/`. No request was issued to the postings endpoint under our generic UA. Not shipped. |
| **Personio (public XML feed)** | 2026-08-11 | `{token}.jobs.personio.com/xml` is reachable, but of 12 candidate boards only a demo tenant returned data, and its apply page (`…/job/{id}`) HTTP-429-redirects to a "Vercel Security Checkpoint" bot challenge — no usable apply URL. Not shipped. |
| **Recruitee — most candidates** | 2026-08-11 | The provider ships (see `SOURCES.md`), but only `channable` returned real listings; 12 of 14 probed tokens 404'd (not Recruitee-hosted) and `personio` was a demo tenant. Only verified boards are seeded. |

**Shipped from this batch:** 43 live-verified ATS company boards added to
`core/sources/seeds.py` (Greenhouse +25, Ashby +16, Lever +2, all robots-clean,
each returning ≥1 live posting on 2026-08-11) plus a new **Recruitee** declarative
source seeded with `channable`.
