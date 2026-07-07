from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RawJob:
    title: str
    company: str
    location: str
    description: str
    url: str
    source: str
    job_type: str = ""
    salary: str = ""
    posted: str = ""
    remote: bool = False
    # True when `description` holds a real job description (not just the title).
    # Used by the matcher to decide whether LLM scoring is worthwhile.
    rich: bool = False

    @property
    def id(self) -> str:
        from models import job_fingerprint

        return job_fingerprint(self.url, self.title, self.company)


class BaseScraper(ABC):
    # Human-facing metadata used by the setup screen.
    label: str = "Source"
    needs_browser: bool = False  # True for Selenium-based scrapers
    recommended: bool = False

    @abstractmethod
    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        ...
