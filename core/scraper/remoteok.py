import requests

from core.scraper.base import BaseScraper, RawJob
from core.scraper.util import human_date, keyword_match, money, strip_html

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class RemoteOKScraper(BaseScraper):
    """RemoteOK public JSON feed — real remote jobs with full descriptions, no key."""

    label = "RemoteOK"
    recommended = True
    API_URL = "https://remoteok.com/api"
    MAX_RESULTS = 60

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        try:
            resp = requests.get(self.API_URL, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            return []

        jobs: list[RawJob] = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("position"):
                continue

            title = str(item.get("position", "")).strip()
            company = str(item.get("company", "")).strip()
            tags = item.get("tags") or []
            description = strip_html(item.get("description", "")) or title
            tag_text = " ".join(str(t) for t in tags)

            if not keyword_match(keywords, title, tag_text, company):
                continue

            url = item.get("url") or item.get("apply_url") or ""
            if url.startswith("/"):
                url = "https://remoteok.com" + url

            jobs.append(
                RawJob(
                    title=title,
                    company=company,
                    location=str(item.get("location") or "Remote").strip() or "Remote",
                    description=description,
                    url=url,
                    source="remoteok",
                    job_type="Remote",
                    salary=money(item.get("salary_min"), item.get("salary_max")),
                    posted=human_date(item.get("date")),
                    remote=True,
                    rich=True,
                )
            )
            if len(jobs) >= self.MAX_RESULTS:
                break

        return jobs
