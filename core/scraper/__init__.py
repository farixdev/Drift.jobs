from core.scraper.arbeitnow import ArbeitnowScraper
from core.scraper.base import BaseScraper
from core.scraper.custom import CustomSiteScraper
from core.scraper.hn import HackerNewsScraper
from core.scraper.indeed import IndeedScraper
from core.scraper.internet_bing import BingInternetSearchScraper
from core.scraper.internet_google import GoogleInternetSearchScraper
from core.scraper.jobicy import JobicyScraper
from core.scraper.linkedin import LinkedInScraper
from core.scraper.remoteok import RemoteOKScraper
from core.scraper.remotive import RemotiveScraper
from core.scraper.themuse import TheMuseScraper
from core.scraper.wwr import WWRScraper
from core.scraper.ziprecruiter import ZipRecruiterScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "jobicy": JobicyScraper,
    "themuse": TheMuseScraper,
    "arbeitnow": ArbeitnowScraper,
    "remoteok": RemoteOKScraper,
    "remotive": RemotiveScraper,
    "wwr": WWRScraper,
    "hn": HackerNewsScraper,
    "linkedin": LinkedInScraper,
    "indeed": IndeedScraper,
    "ziprecruiter": ZipRecruiterScraper,
    "bing": BingInternetSearchScraper,
    "google": GoogleInternetSearchScraper,
}

# Ordered, UI-facing catalog. `recommended` sources filter by the user's role
# server-side (or are clean tech feeds) and return real descriptions with no key.
SOURCES: list[dict] = [
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
    {"key": "linkedin", "label": "LinkedIn", "recommended": False,
     "needs_browser": True, "note": "Needs Chrome · may be blocked"},
    {"key": "indeed", "label": "Indeed", "recommended": False,
     "needs_browser": True, "note": "Needs Chrome · may be blocked"},
    {"key": "ziprecruiter", "label": "ZipRecruiter", "recommended": False,
     "needs_browser": False, "note": "Best-effort HTML"},
    {"key": "bing", "label": "Search the web (Bing)", "recommended": False,
     "needs_browser": False, "note": "Best-effort link discovery"},
    {"key": "google", "label": "Search the web (Google)", "recommended": False,
     "needs_browser": False, "note": "Best-effort · often blocked"},
]

_ALIASES = {
    "weworkremotely": "wwr",
    "weworkremotely.com": "wwr",
    "search internet (bing)": "bing",
    "search internet (google)": "google",
    "hacker news": "hn",
    "the muse": "themuse",
}


def get_custom_scraper(base_url: str) -> CustomSiteScraper:
    return CustomSiteScraper(base_url)


def get_scraper(source: str) -> BaseScraper:
    key = source.lower().strip()
    key = _ALIASES.get(key, key.replace(" ", ""))
    key = _ALIASES.get(key, key)
    if key not in SCRAPERS:
        raise ValueError(f"Unknown job source: {source}")
    return SCRAPERS[key]()
