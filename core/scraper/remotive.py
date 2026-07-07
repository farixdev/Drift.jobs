import requests

from core.scraper.base import BaseScraper, RawJob
from core.scraper.util import human_date, strip_html


class RemotiveScraper(BaseScraper):
    """Remotive open API — curated remote jobs with full descriptions, no key."""

    label = "Remotive"
    recommended = True
    API_URL = "https://remotive.com/api/remote-jobs"
    MAX_RESULTS = 60

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        query = " ".join(keywords[:2])
        try:
            response = requests.get(
                self.API_URL,
                params={"search": query, "limit": self.MAX_RESULTS},
                headers={"User-Agent": "Mozilla/5.0 drift.jobs/2.0"},
                timeout=30,
            )
            response.raise_for_status()
            jobs = response.json().get("jobs", [])
        except Exception:
            return []

        return [
            RawJob(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("candidate_required_location") or "Remote",
                description=strip_html(j.get("description", "")) or j.get("title", ""),
                url=j.get("url", ""),
                source="remotive",
                job_type=j.get("job_type") or "Remote",
                salary=(j.get("salary") or "").strip(),
                posted=human_date(j.get("publication_date")),
                remote=True,
                rich=True,
            )
            for j in jobs
            if j.get("title")
        ]
