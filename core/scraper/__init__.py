from core.scraper.arbeitnow import ArbeitnowScraper
from core.scraper.base import BaseScraper
from core.scraper.custom import CustomSiteScraper
from core.scraper.hn import HackerNewsScraper
from core.scraper.jobicy import JobicyScraper
from core.scraper.remoteok import RemoteOKScraper
from core.scraper.remotive import RemotiveScraper
from core.scraper.themuse import TheMuseScraper
from core.scraper.wwr import WWRScraper

# Legacy first-party scrapers (all key-free, robots-respecting JSON/HTML feeds).
# The 1.x LinkedIn / Indeed / ZipRecruiter / Google / Bing adapters were REMOVED
# in Phase 6 — robots-disallowed and/or shipped detection-evasion. See
# docs/SOURCES_REJECTED.md. New sources are declarative (core/sources/).
SCRAPERS: dict[str, type[BaseScraper]] = {
    "jobicy": JobicyScraper,
    "themuse": TheMuseScraper,
    "arbeitnow": ArbeitnowScraper,
    "remoteok": RemoteOKScraper,
    "remotive": RemotiveScraper,
    "wwr": WWRScraper,
    "hn": HackerNewsScraper,
}

# Ordered, UI-facing catalog. Tier-1 ATS sources (declarative, employer-canonical)
# lead; the key-free aggregator feeds follow.
SOURCES: list[dict] = [
    {"key": "greenhouse", "label": "Greenhouse (ATS)", "recommended": True,
     "needs_browser": False, "note": "Employer-direct postings · full descriptions"},
    {"key": "lever", "label": "Lever (ATS)", "recommended": True,
     "needs_browser": False, "note": "Employer-direct postings · full descriptions"},
    {"key": "ashby", "label": "Ashby (ATS)", "recommended": True,
     "needs_browser": False, "note": "Employer-direct · remote flag + comp"},
    {"key": "workable", "label": "Workable (ATS)", "recommended": True,
     "needs_browser": False, "note": "Employer-direct postings · full descriptions"},
    {"key": "jobicy", "label": "Jobicy", "recommended": True,
     "needs_browser": False, "note": "Remote tech, filtered by your skills"},
    {"key": "themuse", "label": "The Muse", "recommended": True,
     "needs_browser": False, "note": "Huge volume · real companies & levels"},
    {"key": "arbeitnow", "label": "Arbeitnow", "recommended": True,
     "needs_browser": False, "note": "Remote + EU roles · full descriptions"},
    {"key": "remoteok", "label": "RemoteOK", "recommended": False,
     "needs_browser": False, "note": "Newest remote jobs (broad feed)"},
    {"key": "remotive", "label": "Remotive", "recommended": False,
     "needs_browser": False, "note": "Curated remote roles (can be flaky)"},
    {"key": "hn", "label": "Hacker News", "recommended": False,
     "needs_browser": False, "note": "'Who is hiring' · best-effort parsing"},
    {"key": "wwr", "label": "We Work Remotely", "recommended": False,
     "needs_browser": False, "note": "Remote listings"},
]

_ALIASES = {
    "weworkremotely": "wwr",
    "weworkremotely.com": "wwr",
    "hacker news": "hn",
    "the muse": "themuse",
}


def get_custom_scraper(base_url: str) -> CustomSiteScraper:
    return CustomSiteScraper(base_url)


def get_scraper(source: str) -> BaseScraper:
    key = source.lower().strip()
    key = _ALIASES.get(key, key.replace(" ", ""))
    key = _ALIASES.get(key, key)

    # Declarative sources (Phase 6) take precedence and are wrapped to the
    # legacy BaseScraper interface. Imported lazily to avoid an import cycle.
    from core.sources import DEFINITIONS
    if key in DEFINITIONS:
        from core.sources.bridge import DeclarativeScraper
        return DeclarativeScraper(DEFINITIONS[key])

    if key not in SCRAPERS:
        raise ValueError(f"Unknown job source: {source}")
    return SCRAPERS[key]()
