from PyQt5.QtCore import QThread, pyqtSignal

from core import ai_engine, local_engine, parser
from core.config import load_env
from core.scraper import get_custom_scraper
from db import dismissed_ids, init_db, known_ids, record_seen, statuses_for
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
    # Live run signals for the run view: (slug, status, jobs_count) and stats.
    source_event = pyqtSignal(str, str, int)
    stats_signal = pyqtSignal(int, int, int)   # done, total, jobs_total

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
        self._cancel = None

    def stop(self) -> None:
        self._stopped = True
        if self._cancel is not None:
            self._cancel.cancel()

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

            # Phase 8: normalize every result to the canonical schema and cluster
            # duplicates (the same role posted to many boards) into one record.
            from core.dedup import normalize_and_cluster

            clustered = normalize_and_cluster(all_jobs)
            multi = sum(1 for nj in clustered if nj.seen_count > 1)
            self._log(
                f"Normalized + deduped — {len(all_jobs)} → {len(clustered)} unique roles"
                + (f" ({multi} seen on multiple sites)" if multi else ""),
                "done",
            )

            # Drop jobs the user already dismissed (matched by content fingerprint).
            dismissed = dismissed_ids()
            if dismissed:
                before = len(clustered)
                clustered = [nj for nj in clustered if nj.fingerprint not in dismissed]
                hidden = before - len(clustered)
                if hidden:
                    self._log(f"Hid {hidden} previously dismissed job(s)", "done")

            prior = known_ids()  # what we'd seen before THIS scan

            # Phase 8 three-stage ranking: BM25 lexical → semantic → LLM rerank,
            # blended with freshness and filtered by the blocklist. Produces Jobs
            # with per-dimension sub-scores + a rationale (explainable scoring).
            from core.ranking import rank_jobs

            self._log(f"Ranking {len(clustered)} jobs…", "active")
            self.progress_signal.emit(80)
            use_llm = ai_engine.has_api_key()
            scored = rank_jobs(clustered, resume_text, skills=skills,
                               keywords=keywords, use_llm=use_llm, log=self._log)

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

        # Route all selected sources through the Phase-7 concurrent engine:
        # bounded pool, per-domain rate limiting, priority (APIs first), retries,
        # circuit breaker, checkpointing, streaming, and cooperative cancel.
        from core.engine import CancelToken, RunConfig, ScanEngine
        from core.engine import events as ev
        from core.sources import SearchCriteria, resolve_selection

        keys = [SOURCE_KEYS.get(s, s.lower().replace(" ", "")) for s in self.selected_sources]
        definitions = resolve_selection([k for k in keys if k])
        if not definitions:
            definitions = resolve_selection(["remoteok"])

        self._cancel = CancelToken()
        criteria = SearchCriteria.from_legacy(keywords, location)
        engine = ScanEngine(RunConfig.load(), on_event=self._on_engine_event,
                            cancel=self._cancel)
        self._log(f"Searching {len(definitions)} source(s)…", "active")
        summary = self._engine_summary = engine.run(definitions, criteria)
        self._log(
            f"Found {summary.total_jobs} unique jobs · "
            f"{summary.sources_succeeded}/{summary.sources_attempted} sources ok"
            + (f" · {summary.sources_blocked} blocked" if summary.sources_blocked else ""),
            "done",
        )
        return summary.jobs

    def _on_engine_event(self, event) -> None:
        """Forward engine events to the run view. Runs on engine pool threads —
        Qt queues the signals to the UI thread."""
        from core.engine import events as ev
        t = event.type
        if t == ev.SOURCE_QUEUED:
            self.source_event.emit(event.source, "queued", 0)
        elif t == ev.SOURCE_RUNNING:
            self.source_event.emit(event.source, "running", 0)
        elif t == ev.SOURCE_DONE:
            p = event.payload
            self.source_event.emit(event.source, p["status"], p["jobs"])
            if p["status"] != "done":
                detail = p.get("error_class") or "error"
                http = f" HTTP {p['http_status']}" if p.get("http_status") else ""
                self._log(f"{event.source} — {p['status']} ({detail}{http})", "done")
            else:
                self._log(f"{event.source} — {p['jobs']} listings", "done")
        elif t == ev.PROGRESS:
            pl = event.payload
            self.stats_signal.emit(pl["done"], pl["total"], 0)
            self.progress_signal.emit(30 + int(45 * pl["done"] / max(1, pl["total"])))
        elif t == ev.WIDENED:
            self._log(f"Widened search — {event.payload['description']}", "done")
