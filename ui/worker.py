from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import QThread, pyqtSignal

from core import ai_engine, local_engine, matcher, parser
from core.config import load_env
from core.scraper import get_custom_scraper, get_scraper
from db import dedupe_by_url, dismissed_ids, init_db, known_ids, record_seen, statuses_for
from models import STATUS_NEW

# Legacy label -> key mapping (setup screen now emits keys directly).
SOURCE_KEYS = {
    "Remotive": "remotive",
    "RemoteOK": "remoteok",
    "Arbeitnow": "arbeitnow",
    "We Work Remotely": "wwr",
}


class ScanWorker(QThread):
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int)
    subtitle_signal = pyqtSignal(str)
    done_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        resume_path: str,
        selected_sources: list[str],
        threshold: int,
        resume_text: str = "",
        custom_url: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.resume_path = resume_path
        self.selected_sources = selected_sources
        self.threshold = threshold
        self.resume_text = resume_text
        self.custom_url = custom_url
        self.parsed_skills: list[str] = []
        self.parsed_resume_text: str = resume_text
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def _log(self, message: str, status: str = "active") -> None:
        self.log_signal.emit(message, status)

    def run(self) -> None:
        try:
            load_env()
            init_db()

            resume_text = (self.resume_text or "").strip()
            if len(resume_text) < 20:
                self._log("Reading resume…", "active")
                resume_text = parser.extract(self.resume_path)
            if len(resume_text.strip()) < 20:
                raise RuntimeError(
                    "Could not extract text from resume. Use a text-based PDF, DOC, or DOCX."
                )

            self._log("Parsing resume…", "active")
            self.parsed_resume_text = resume_text
            parsed = self._parse(resume_text)
            skills = parsed["skills"]
            self.parsed_skills = skills
            location = parsed["location"]
            keywords = parsed["keywords"]
            role_hint = ", ".join(skills[:2]) if skills else "Your profile"
            self.subtitle_signal.emit(f"{role_hint} · {location}")
            self._log(f"Resume parsed — {len(skills)} skills found", "done")
            self.progress_signal.emit(18)
            self._log(f"Keywords — {', '.join(keywords[:4])}", "done")
            self.progress_signal.emit(30)

            all_jobs = self._scrape(keywords, location)

            if self._stopped:
                self._log("Stopped — scoring what we found so far…", "active")

            all_jobs = dedupe_by_url(all_jobs)

            # Drop jobs the user already dismissed in a previous scan.
            dismissed = dismissed_ids()
            if dismissed:
                before = len(all_jobs)
                all_jobs = [j for j in all_jobs if j.id not in dismissed]
                hidden = before - len(all_jobs)
                if hidden:
                    self._log(f"Hid {hidden} previously dismissed job(s)", "done")

            prior = known_ids()  # what we'd seen before THIS scan

            self._log(f"Scoring {len(all_jobs)} jobs…", "active")
            self.progress_signal.emit(80)
            use_llm = ai_engine.has_api_key()
            scored = matcher.score_all(
                all_jobs, resume_text, skills=skills, use_llm=use_llm,
                keywords=keywords, log=self._log,
            )

            # Annotate new-vs-seen + persisted status, then remember them.
            status_map = statuses_for([j.job_id for j in scored])
            for job in scored:
                job.is_new = job.job_id not in prior
                job.status = status_map.get(job.job_id, STATUS_NEW)
            record_seen(scored)

            above = sum(1 for j in scored if j.score >= self.threshold)
            self._log(
                f"Done — {above} match {self.threshold}%+ · {len(scored)} scored total",
                "done",
            )
            self.progress_signal.emit(100)
            self.done_signal.emit(scored)
        except Exception as exc:
            self.error_signal.emit(str(exc))

    def _parse(self, resume_text: str) -> dict:
        if ai_engine.has_api_key():
            try:
                return ai_engine.parse_resume(resume_text)
            except Exception as exc:
                self._log(f"AI parse failed ({type(exc).__name__}) — using local parser", "done")
        return local_engine.parse_resume(resume_text)

    def _scrape(self, keywords: list[str], location: str) -> list:
        if self.custom_url:
            label = self.custom_url.replace("https://", "")
            self._log(f"Fetching {label}…", "active")
            try:
                jobs = get_custom_scraper(self.custom_url).search(keywords, location)
            except Exception as exc:
                self._log(f"{label} failed — {type(exc).__name__}", "done")
                jobs = []
            self._log(
                f"{label} — {len(jobs)} roles found"
                if jobs
                else f"{label} — no listings found on /jobs page",
                "done",
            )
            self.progress_signal.emit(75)
            return jobs

        sources = [SOURCE_KEYS.get(s, s.lower().replace(" ", "")) for s in self.selected_sources]
        sources = [s for s in sources if s] or ["remoteok"]
        total = len(sources)
        collected: list = []
        done = 0

        def run_one(key: str):
            try:
                scraper = get_scraper(key)
                jobs = scraper.search(keywords, location)
                # Declarative sources stash a SourceResult with real diagnostics.
                return key, jobs, getattr(scraper, "last_result", None)
            except Exception as exc:  # keep the scan alive on a single failure
                return key, exc, None

        self._log(f"Searching {total} source(s) in parallel…", "active")
        with ThreadPoolExecutor(max_workers=min(total, 4)) as pool:
            futures = {pool.submit(run_one, key): key for key in sources}
            for future in as_completed(futures):
                key, result, diag = future.result()
                done += 1
                if isinstance(result, Exception):
                    self._log(f"{key} — failed ({type(result).__name__})", "done")
                elif diag is not None and diag.status not in ("done",):
                    # Surface HTTP status + error class + timestamp — no silent failures.
                    self._log(
                        f"{key} — {diag.status}"
                        f" ({diag.error_class or 'error'}"
                        f"{f' HTTP {diag.http_status}' if diag.http_status else ''})"
                        f" · {diag.finished_at[11:19]}",
                        "done",
                    )
                else:
                    collected.extend(result)
                    self._log(f"{key} — {len(result)} listings ({len(collected)} total)", "done")
                self.progress_signal.emit(30 + int(45 * done / total))
                if self._stopped:
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
        return collected
