from core.scraper.arbeitnow import ArbeitnowScraper
from core.scraper.base import BaseScraper
from core.scraper.custom import CustomSiteScraper
from core.scraper.indeed import IndeedScraper
from core.scraper.internet_bing import BingInternetSearchScraper
from core.scraper.internet_google import GoogleInternetSearchScraper
from core.scraper.linkedin import LinkedInScraper
from core.scraper.remoteok import RemoteOKScraper
from core.scraper.remotive import RemotiveScraper
from core.scraper.wwr import WWRScraper
from core.scraper.ziprecruiter import ZipRecruiterScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "remoteok": RemoteOKScraper,
    "remotive": RemotiveScraper,
    "arbeitnow": ArbeitnowScraper,
    "wwr": WWRScraper,
    "linkedin": LinkedInScraper,
    "indeed": IndeedScraper,
    "ziprecruiter": ZipRecruiterScraper,
    "bing": BingInternetSearchScraper,
    "google": GoogleInternetSearchScraper,
}

# Ordered, UI-facing catalog. `recommended` sources are fast, key-free JSON APIs
# that return real descriptions; `needs_browser` ones drive Chrome and can be
# blocked or slow.
SOURCES: list[dict] = [
    {"key": "remoteok", "label": "RemoteOK", "recommended": True,
     "needs_browser": False, "note": "Remote tech jobs · full descriptions"},
    {"key": "remotive", "label": "Remotive", "recommended": True,
     "needs_browser": False, "note": "Curated remote roles · full descriptions"},
    {"key": "arbeitnow", "label": "Arbeitnow", "recommended": True,
     "needs_browser": False, "note": "Remote + EU roles · full descriptions"},
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

# Legacy label -> key aliases (kept so older configs keep working).
_ALIASES = {
    "weworkremotely": "wwr",
    "weworkremotely.com": "wwr",
    "search internet (bing)": "bing",
    "search internet (google)": "google",
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
