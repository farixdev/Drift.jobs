import requests

from core.scraper.base import BaseScraper, RawJob
from core.scraper.util import human_date, strip_html

_HEADERS = {"User-Agent": "Mozilla/5.0 drift.jobs/2.0", "Accept": "application/json"}

# Candidate skill -> a valid The Muse category.
_CATEGORY_MAP = {
    "machine learning": "Data Science", "tensorflow": "Data Science",
    "pytorch": "Data Science", "pandas": "Data Science", "data analysis": "Data Science",
    "figma": "Design", "ui/ux": "Design", "ux": "Design", "ui design": "Design",
    "docker": "IT", "kubernetes": "IT", "terraform": "IT", "devops": "IT",
    "aws": "IT", "linux": "IT",
}
_DEFAULT_CATEGORY = "Software Engineering"


class TheMuseScraper(BaseScraper):
    """The Muse public jobs API — large volume, category + level filtering, no key."""

    label = "The Muse"
    recommended = True
    API_URL = "https://www.themuse.com/api/public/jobs"
    MAX_PAGES = 2
    MAX_RESULTS = 50

    def _categories(self, skills: list[str]) -> list[str]:
        cats = [_DEFAULT_CATEGORY]
        for skill in skills:
            cat = _CATEGORY_MAP.get(skill.lower())
            if cat and cat not in cats:
                cats.append(cat)
            if len(cats) >= 2:
                break
        return cats

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        skill_words = [w for kw in keywords for w in kw.split() if len(w) > 1]
        params = [("category", c) for c in self._categories(skill_words)]
        jobs: list[RawJob] = []
        seen: set[str] = set()

        for page in range(1, self.MAX_PAGES + 1):
            try:
                resp = requests.get(
                    self.API_URL,
                    params=params + [("page", page)],
                    headers=_HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception:
                break

            for item in payload.get("results", []):
                refs = item.get("refs") or {}
                url = str(refs.get("landing_page") or "").strip()
                key = url.lower().rstrip("/")
                if not url or key in seen:
                    continue
                seen.add(key)

                locs = [l.get("name") for l in (item.get("locations") or []) if l.get("name")]
                levels = [l.get("name") for l in (item.get("levels") or []) if l.get("name")]
                is_remote = any("remote" in (l or "").lower() for l in locs)
                jobs.append(
                    RawJob(
                        title=str(item.get("name", "")).strip(),
                        company=str((item.get("company") or {}).get("name", "")).strip(),
                        location=", ".join(locs[:2]) or ("Remote" if is_remote else ""),
                        description=strip_html(item.get("contents", "")) or item.get("name", ""),
                        url=url,
                        source="themuse",
                        job_type=item.get("type") or (levels[0] if levels else ""),
                        posted=human_date(item.get("publication_date")),
                        remote=is_remote,
                        rich=True,
                    )
                )
                if len(jobs) >= self.MAX_RESULTS:
                    return jobs
        return jobs
