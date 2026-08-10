"""Run one declarative source against criteria → a SourceResult.

Engine-side, source-agnostic: map criteria to request specs, fetch each
(robots-checked, honest UA, bounded concurrency), parse via the definition's
parser, keyword-filter, cap, and record health. Failures are captured with their
HTTP status and error class — never swallowed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from core.scraper.util import keyword_match
from core.sources import health, http, robots
from core.sources.spec import SearchCriteria, SourceDefinition, SourceResult


def run_source(defn: SourceDefinition, criteria: SearchCriteria) -> SourceResult:
    started = datetime.now(timezone.utc)
    health.ensure_source(defn)

    if not defn.enabled:
        return _result(defn, "skipped", started, error_class="disabled",
                       error_detail="source disabled in definition")
    if not health.allow(defn.slug):
        return _result(defn, "skipped", started, error_class="circuit_open",
                       error_detail="breaker open after repeated failures")

    try:
        specs = defn.query_mapper(criteria)
    except Exception as exc:  # a broken mapper must not kill the run
        health.record_failure(defn.slug, f"query_mapper: {exc}")
        return _result(defn, "failed", started, error_class=type(exc).__name__,
                       error_detail=str(exc)[:200])

    jobs: list = []
    errors: list[tuple[int | None, str, str]] = []
    boards_ok = 0

    def fetch_one(spec):
        if defn.robots_check and not robots.allowed(spec.url):
            return ("blocked", None, "RobotsDisallowed", spec.url, [])
        f = http.get(spec.url, method=spec.method, headers=spec.headers,
                     params=spec.params, json_body=spec.json_body)
        if not f.ok:
            return ("failed", f.status, f.error_class, f.error_detail, [])
        try:
            parsed = defn.response_parser(f.json, spec)
        except Exception as exc:
            return ("failed", f.status, type(exc).__name__, str(exc)[:160], [])
        return ("done", f.status, "", "", parsed)

    workers = max(1, min(defn.concurrency_limit, len(specs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for status, code, ecls, edetail, parsed in pool.map(fetch_one, specs):
            if status == "done":
                boards_ok += 1
                jobs.extend(parsed)
            else:
                errors.append((code, ecls, edetail))

    # keyword filter + cap
    if criteria.keywords:
        jobs = [j for j in jobs
                if keyword_match(criteria.keywords, j.title, j.description, j.company)]
    jobs = jobs[: criteria.max_per_source]

    if boards_ok == 0 and errors:
        code, ecls, edetail = errors[0]
        # blocked if every failure was robots
        status = "blocked" if all(e[1] == "RobotsDisallowed" for e in errors) else "failed"
        health.record_failure(defn.slug, f"{ecls}: {edetail}")
        return _result(defn, status, started, http_status=code, error_class=ecls,
                       error_detail=edetail, boards_attempted=len(specs))

    health.record_success(defn.slug)
    return _result(defn, "done", started, jobs=jobs, boards_attempted=len(specs),
                   boards_succeeded=boards_ok,
                   error_detail=(f"{len(errors)} board(s) errored" if errors else ""))


def _result(defn, status, started, **kw) -> SourceResult:
    now = datetime.now(timezone.utc)
    return SourceResult(
        slug=defn.slug, status=status,
        duration_ms=int((now - started).total_seconds() * 1000),
        finished_at=now.replace(microsecond=0).isoformat(), **kw)
