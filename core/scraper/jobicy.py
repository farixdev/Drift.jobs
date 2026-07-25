import requests

from core.scraper.base import BaseScraper, RawJob
from core.scraper.util import human_date, strip_html

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Candidate skill -> a Jobicy tag slug that actually filters server-side.
_TAG_MAP = {
    "python": "python", "django": "python", "flask": "python", "fastapi": "python",
    "javascript": "javascript", "typescript": "javascript", "react": "react",
    "reactjs": "react", "vue": "javascript", "angular": "javascript",
    "node.js": "node", "nodejs": "node", "node": "node",
    "php": "php", "laravel": "php", "ruby": "ruby", "rails": "ruby",
    "go": "golang", "golang": "golang", "java": "java", "kotlin": "java",
    "c#": "dotnet", ".net": "dotnet", "swift": "ios", "ios": "ios",
    "android": "android", "flutter": "android",
    "docker": "devops", "kubernetes": "devops", "aws": "devops", "azure": "devops",
    "terraform": "devops", "devops": "devops", "linux": "sysadmin",
    "machine learning": "data-science", "tensorflow": "data-science",
    "pytorch": "data-science", "pandas": "data-science", "sql": "data-science",
    "figma": "design", "ui/ux": "design", "ux": "design",
    "marketing": "marketing", "seo": "seo", "sales": "sales",
}


class JobicyScraper(BaseScraper):
    """Jobicy remote-jobs API — real tag filtering, full descriptions, no key."""

    label = "Jobicy"
    recommended = True
    API_URL = "https://jobicy.com/api/v2/remote-jobs"
    MAX_RESULTS = 50

    def _tags(self, skills: list[str]) -> list[str]:
        tags: list[str] = []
        for skill in skills:
            tag = _TAG_MAP.get(skill.lower())
            if tag and tag not in tags:
                tags.append(tag)
            if len(tags) >= 2:
                break
        return tags or ["dev"]

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        # keywords look like ["Python developer", "Backend Engineer"] — mine skill words.
        skill_words = [w for kw in keywords for w in kw.split() if len(w) > 1]
        jobs: list[RawJob] = []
        seen: set[str] = set()

        for tag in self._tags(skill_words):
            try:
                resp = requests.get(
                    self.API_URL,
                    params={"count": 40, "tag": tag},
                    headers=_HEADERS,
                    timeout=30,
                )
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                payload = resp.json()
            except Exception:
                continue

            for item in payload.get("jobs", []):
                url = str(item.get("url") or "").strip()
                key = url.lower().rstrip("/")
                if not url or key in seen:
                    continue
                seen.add(key)
                jt = item.get("jobType")
                job_type = ", ".join(jt) if isinstance(jt, list) else str(jt or "")
                jobs.append(
                    RawJob(
                        title=str(item.get("jobTitle", "")).strip(),
                        company=str(item.get("companyName", "")).strip(),
                        location=str(item.get("jobGeo") or "Remote").strip() or "Remote",
                        description=strip_html(item.get("jobDescription", ""))
                        or item.get("jobExcerpt", "")
                        or item.get("jobTitle", ""),
                        url=url,
                        source="jobicy",
                        job_type=job_type or (item.get("jobLevel") or ""),
                        posted=human_date(item.get("pubDate")),
                        remote=True,
                        rich=True,
                    )
                )
                if len(jobs) >= self.MAX_RESULTS:
                    return jobs
        return jobs
