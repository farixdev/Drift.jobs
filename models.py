import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

# Per-job lifecycle states used across the UI and the local database.
STATUS_NEW = "new"
STATUS_SAVED = "saved"
STATUS_APPLIED = "applied"
STATUS_DISMISSED = "dismissed"
ALL_STATUSES = (STATUS_NEW, STATUS_SAVED, STATUS_APPLIED, STATUS_DISMISSED)


def job_fingerprint(url: str, title: str = "", company: str = "") -> str:
    """Stable id for a job, so we can dedupe and track state across scans.

    Prefer the URL; fall back to title+company for sources with unstable links.
    """
    basis = (url or "").strip().lower().rstrip("/")
    if not basis:
        basis = f"{(title or '').strip().lower()}::{(company or '').strip().lower()}"
    return hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()[:16]


@dataclass
class Job:
    title: str
    company: str
    location: str
    job_type: str
    url: str
    source: str
    description: str = ""
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    score: int = 0
    summary: str = ""
    verdict: str = ""
    salary: str = ""
    posted: str = ""
    remote: bool = False
    status: str = STATUS_NEW
    is_new: bool = True
    cover_letter: str = ""
    scraped_at: datetime = field(default_factory=datetime.now)

    @property
    def job_id(self) -> str:
        return job_fingerprint(self.url, self.title, self.company)
