"""ScanEngine — concurrent, streaming source execution.

Runs many sources through a bounded worker pool with per-domain rate limiting and
a priority order (clean APIs first, browser adapters last). Streams each source's
results the moment it returns, checkpoints to the DB, honours a global timeout and
cooperative cancellation, and — when `min_results` isn't met — widens the query
and reruns, reporting exactly what was relaxed.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.engine import checkpoint, events
from core.engine.cancellation import CancelToken
from core.engine.config import RunConfig
from core.engine.events import RunEvent, RunSummary
from core.engine.ratelimit import DomainLimiter
from core.sources import SearchCriteria, run_source
from core.sources.runner import run_legacy
from core.sources.spec import SourceDefinition

# Lower number = higher priority (runs first).
_PRIORITY = {"api": 0, "rss": 1, "search_engine": 2, "browser": 3}


def _noop(_event):
    pass


class ScanEngine:
    def __init__(self, config: RunConfig | None = None, on_event=None,
                 cancel: CancelToken | None = None):
        self.config = (config or RunConfig.load()).clamped()
        self.on_event = on_event or _noop
        self.cancel = cancel or CancelToken()
        self.limiter = DomainLimiter(per_domain_concurrency=self.config.per_domain_concurrency)

    # -- public ------------------------------------------------------------ #
    def run(self, definitions: list[SourceDefinition], criteria: SearchCriteria,
            *, resume_run_id: int | None = None) -> RunSummary:
        start = time.monotonic()
        ordered = sorted(definitions, key=lambda d: _PRIORITY.get(d.adapter_type, 9))

        run_id = resume_run_id or checkpoint.create_run(self.config)
        already = checkpoint.done_sources(run_id) if resume_run_id else set()
        pending = [d for d in ordered if d.slug not in already]

        self._emit(events.RUN_STARTED, payload={"run_id": run_id, "total": len(pending),
                                                "resumed": bool(resume_run_id)})

        all_jobs: list = []
        results: list = []
        widen_rounds = 0
        active_criteria = criteria

        while True:
            batch = self._run_pass(pending, active_criteria, run_id, start)
            results.extend(batch)
            for r in batch:
                all_jobs.extend(r.jobs)

            unique = _dedupe(all_jobs)
            if self.config.max_results and len(unique) > self.config.max_results:
                unique = unique[: self.config.max_results]
            met = self.config.min_results and len(unique) >= self.config.min_results
            exhausted_time = (time.monotonic() - start) >= self.config.run_timeout_s

            if (self.cancel.cancelled or met or exhausted_time
                    or not self.config.widen or self.config.min_results == 0
                    or widen_rounds >= self.config.max_widen_rounds):
                break

            widened = _widen(active_criteria)
            if widened is None:
                break
            active_criteria, what = widened
            widen_rounds += 1
            self._emit(events.WIDENED, payload={"description": what, "round": widen_rounds})
            pending = ordered  # rerun all sources with the relaxed criteria

        unique = _dedupe(all_jobs)
        if self.config.max_results:
            unique = unique[: self.config.max_results]

        summary = RunSummary(
            run_id=run_id,
            status="cancelled" if self.cancel.cancelled else
                   ("timeout" if (time.monotonic() - start) >= self.config.run_timeout_s else "completed"),
            total_jobs=len(unique),
            sources_attempted=len(results),
            sources_succeeded=sum(1 for r in results if r.status == "done"),
            sources_failed=sum(1 for r in results if r.status == "failed"),
            sources_blocked=sum(1 for r in results if r.status == "blocked"),
            widen_rounds=widen_rounds,
            elapsed_s=round(time.monotonic() - start, 2),
            per_source=results,
            jobs=unique,
        )
        checkpoint.finalize_run(run_id, summary)
        self._emit(events.RUN_FINISHED, payload=summary)
        return summary

    # -- internals --------------------------------------------------------- #
    def _run_pass(self, definitions, criteria, run_id, start) -> list:
        total = len(definitions)
        if total == 0:
            return []
        # Ensure the source rows exist before queueing so run_source_result rows
        # get a valid source_id (needed for checkpoint/resume joins).
        from core.sources import health
        for d in definitions:
            health.ensure_source(d)
        rsr_ids = {d.slug: checkpoint.queue_source(run_id, d.slug) for d in definitions}
        for d in definitions:
            self._emit(events.SOURCE_QUEUED, source=d.slug)

        results: list = []
        done = 0
        deadline = start + self.config.run_timeout_s

        def task(defn):
            self._emit(events.SOURCE_RUNNING, source=defn.slug)
            checkpoint.mark_running(rsr_ids[defn.slug])
            src_cancel = _linked_timeout(self.cancel, self.config.source_timeout_s)
            runner = run_legacy if defn.legacy_slug else run_source
            result = runner(defn, criteria, retries=self.config.max_retries,
                            limiter=self.limiter, cancel=src_cancel,
                            proxy=self.config.proxy)
            checkpoint.save_source_result(run_id, rsr_ids[defn.slug], result)
            return result

        workers = max(1, min(self.config.global_concurrency, total))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(task, d): d for d in definitions}
            try:
                for fut in as_completed(futures, timeout=max(0.1, deadline - time.monotonic())):
                    result = fut.result()
                    results.append(result)
                    done += 1
                    self._emit(events.SOURCE_RESULT, source=result.slug, payload=result)
                    self._emit(events.SOURCE_DONE, source=result.slug, payload={
                        "status": result.status, "jobs": len(result.jobs),
                        "error_class": result.error_class, "http_status": result.http_status})
                    self._emit(events.PROGRESS, payload={
                        "done": done, "total": total,
                        "elapsed_s": round(time.monotonic() - start, 1),
                        "eta_s": _eta(done, total, time.monotonic() - start)})
                    if self.cancel.cancelled:
                        break
            except TimeoutError:
                self.cancel.cancel()  # global timeout: wind down remaining sources
                self._emit(events.LOG, payload={"message": "Run timeout — stopping remaining sources"})
                for fut in futures:  # drain whatever finished
                    if fut.done() and futures[fut].slug not in {r.slug for r in results}:
                        try:
                            results.append(fut.result(timeout=0))
                        except Exception:
                            pass
        return results

    def _emit(self, etype, source="", payload=None):
        try:
            self.on_event(RunEvent(type=etype, source=source, payload=payload))
        except Exception:
            pass  # a broken UI callback must never kill a run


def _linked_timeout(parent: CancelToken, seconds: int) -> CancelToken:
    """A child cancel that fires when the parent cancels OR after `seconds`."""
    child = CancelToken()

    def _watch():
        if parent.wait(seconds):  # parent cancelled first
            child.cancel()
        else:
            child.cancel()        # per-source timeout elapsed
    t = threading.Thread(target=_watch, daemon=True)
    t.start()
    return child


def _dedupe(raw_jobs) -> list:
    seen: set[str] = set()
    out = []
    for j in raw_jobs:
        if j.id in seen:
            continue
        seen.add(j.id)
        out.append(j)
    return out


def _eta(done, total, elapsed) -> float:
    if done == 0:
        return 0.0
    return round((elapsed / done) * (total - done), 1)


def _widen(criteria: SearchCriteria):
    """Relax the query one step. Returns (new_criteria, human_description) or None.

    Order (least to most impactful): drop nice-to-have keywords, extend the date
    window, then loosen location mode, country, and the salary floor, and finally
    drop a plain keyword as a last resort.
    """
    import dataclasses as _dc
    r = _dc.replace
    if criteria.keywords_nice:
        return r(criteria, keywords_nice=[]), \
            f"dropped {len(criteria.keywords_nice)} nice-to-have keyword(s)"
    if criteria.posted_within_days and criteria.posted_within_days < 30:
        nxt = {1: 3, 3: 7, 7: 14, 14: 30}.get(criteria.posted_within_days, 30)
        return r(criteria, posted_within_days=nxt), f"extended freshness to {nxt} days"
    if criteria.posted_within_days == 30:
        return r(criteria, posted_within_days=None), "removed the date filter"
    if criteria.location_mode and criteria.location_mode != "any":
        return r(criteria, location_mode="any"), "removed the location-mode filter"
    if criteria.countries:
        return r(criteria, countries=[]), "removed the country filter"
    if criteria.salary_min:
        return r(criteria, salary_min=None), "removed the salary floor"
    if criteria.keywords and len(criteria.keywords) > 1:
        dropped = criteria.keywords[-1]
        return r(criteria, keywords=criteria.keywords[:-1]), f"dropped keyword '{dropped}'"
    if criteria.remote is not None:
        return r(criteria, remote=None), "removed the remote/on-site filter"
    return None
