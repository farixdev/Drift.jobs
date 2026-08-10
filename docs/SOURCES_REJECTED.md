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
