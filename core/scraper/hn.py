import re

import requests

from core.scraper.base import BaseScraper, RawJob
from core.scraper.util import keyword_match, strip_html

_HEADERS = {"User-Agent": "Mozilla/5.0 drift.jobs/2.0", "Accept": "application/json"}
_SALARY_RE = re.compile(r"(\$\s?[\d]{2,3}[kK][^|–—\n]*|\$\s?[\d,]{4,}[^|–—\n]*)")
_REMOTE_RE = re.compile(r"(?i)\b(remote|hybrid|onsite|on-site)\b")
_LOC_RE = re.compile(r"(?i)\b(remote|hybrid|onsite|anywhere|[A-Z][a-z]+,\s*[A-Z]{2}\b|[A-Z][a-z]+,\s*[A-Z][a-z]+)")
_ROLE_RE = re.compile(
    r"(?i)\b(engineer|developer|dev|designer|scientist|manager|lead|architect|"
    r"devops|sre|programmer|analyst|researcher|founder|cto|head of|director|"
    r"backend|frontend|full[\s-]?stack|data|ml|ai|security|qa|product|"
    r"consultant|specialist|administrator|intern)\b"
)


class HackerNewsScraper(BaseScraper):
    """Individual roles mined from the current HN 'Ask HN: Who is hiring?' thread
    via the Algolia API — fresh, structured, full-text searchable, never blocked."""

    label = "Hacker News"
    recommended = False
    BY_DATE = "https://hn.algolia.com/api/v1/search_by_date"
    SEARCH = "https://hn.algolia.com/api/v1/search"
    MAX_RESULTS = 40

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        story_id = self._latest_thread()
        if not story_id:
            return []
        query = " ".join(
            w for kw in keywords[:2] for w in kw.split() if len(w) > 2
        )[:40] or "engineer"
        try:
            hits = requests.get(
                self.SEARCH,
                params={"tags": f"comment,story_{story_id}", "query": query,
                        "hitsPerPage": 60},
                headers=_HEADERS,
                timeout=30,
            ).json().get("hits", [])
        except Exception:
            return []

        jobs: list[RawJob] = []
        for c in hits:
            job = self._parse_comment(c, keywords)
            if job:
                jobs.append(job)
            if len(jobs) >= self.MAX_RESULTS:
                break
        return jobs

    def _latest_thread(self) -> str | None:
        try:
            hits = requests.get(
                self.BY_DATE,
                params={"tags": "story,author_whoishiring", "hitsPerPage": 6},
                headers=_HEADERS,
                timeout=30,
            ).json().get("hits", [])
        except Exception:
            return None
        for h in hits:
            if "who is hiring" in (h.get("title") or "").lower():
                return h.get("objectID")
        return None

    def _parse_comment(self, comment: dict, keywords: list[str]) -> RawJob | None:
        text = strip_html((comment.get("comment_text") or "").replace("&#x2F;", "/"))
        if len(text) < 40:
            return None
        head = text.split("\n")[0]
        parts = [p.strip() for p in re.split(r"[|]", head) if p.strip()]
        if len(parts) < 2:
            # Some posts use dashes; fall back only if a role is detectable.
            parts = [p.strip() for p in re.split(r"[|–—]", head) if p.strip()]
        if len(parts) < 2 or not keyword_match(keywords, head, text):
            return None

        company = re.sub(r"\s*\(YC\s+\w+\)\s*", " ", parts[0]).strip()[:80]
        # Company must look like a name, not a sentence or salary line.
        if len(company) > 45 or "$" in company or not re.search(r"[A-Za-z]", company):
            return None
        # Pick the part that reads like a job title; skip if none (keeps titles clean).
        role = next(
            (p for p in parts[1:]
             if _ROLE_RE.search(p) and not _LOC_RE.match(p)
             and "$" not in p and not p.lower().startswith(("multiple", "we ", "our "))
             and len(p) < 70),
            "",
        )
        if not role:
            return None
        title = role[:120]

        location = next((p[:60] for p in parts[1:] if p != role and _LOC_RE.search(p)), "")
        m = _SALARY_RE.search(head) or _SALARY_RE.search(text[:400])
        salary = m.group(1).strip()[:40] if m else ""

        oid = comment.get("objectID")
        return RawJob(
            title=title,
            company=company,
            location=location or ("Remote" if _REMOTE_RE.search(text) else ""),
            description=text[:1800],
            url=f"https://news.ycombinator.com/item?id={oid}",
            source="hn",
            salary=salary,
            remote=bool(_REMOTE_RE.search(text)),
            rich=True,
        )
