import requests

from core.scraper.base import BaseScraper, RawJob
from core.scraper.util import human_date, keyword_match, strip_html

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class ArbeitnowScraper(BaseScraper):
    """Arbeitnow public job-board API — full descriptions, remote + EU roles, no key."""

    label = "Arbeitnow"
    recommended = True
    API_URL = "https://www.arbeitnow.com/api/job-board-api"
    MAX_PAGES = 3
    MAX_RESULTS = 60

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen: set[str] = set()
        url = self.API_URL

        for _ in range(self.MAX_PAGES):
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=30)
                resp.raise_for_status()
                payload = resp.json()
            except Exception:
                break

            for item in payload.get("data", []):
                if not isinstance(item, dict) or not item.get("title"):
                    continue

                title = str(item.get("title", "")).strip()
                company = str(item.get("company_name", "")).strip()
                tags = item.get("tags") or []
                job_types = item.get("job_types") or []
                description = strip_html(item.get("description", "")) or title
                tag_text = " ".join(str(t) for t in list(tags) + list(job_types))

                if not keyword_match(keywords, title, tag_text, company):
                    continue

                link = str(item.get("url") or "").strip()
                key = link.lower().rstrip("/")
                if not link or key in seen:
                    continue
                seen.add(key)

                remote = bool(item.get("remote"))
                jobs.append(
                    RawJob(
                        title=title,
                        company=company,
                        location=str(item.get("location") or "").strip()
                        or ("Remote" if remote else ""),
                        description=description,
                        url=link,
                        source="arbeitnow",
                        job_type=", ".join(str(t) for t in job_types)
                        or ("Remote" if remote else ""),
                        posted=human_date(item.get("created_at")),
                        remote=remote,
                        rich=True,
                    )
                )
                if len(jobs) >= self.MAX_RESULTS:
                    return jobs

            url = (payload.get("links") or {}).get("next") or ""
            if not url:
                break

        return jobs
