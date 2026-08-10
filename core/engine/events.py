"""Engine events — the stream the UI renders.

The engine calls a single `on_event(RunEvent)` callback as work progresses, so
results flow to the UI the moment each source returns rather than at the end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Event types
RUN_STARTED = "run_started"
SOURCE_QUEUED = "source_queued"
SOURCE_RUNNING = "source_running"
SOURCE_RESULT = "source_result"     # payload: SourceResult (jobs streamed)
SOURCE_DONE = "source_done"         # payload: {status, counts, error, http_status}
WIDENED = "widened"                 # payload: {description, round}
PROGRESS = "progress"               # payload: {done, total, elapsed_s, eta_s}
LOG = "log"                         # payload: {message}
RUN_FINISHED = "run_finished"       # payload: RunSummary


@dataclass
class RunEvent:
    type: str
    source: str = ""
    payload: Any = None


@dataclass
class RunSummary:
    run_id: int | None
    status: str                      # completed | cancelled | timeout
    total_jobs: int = 0
    sources_attempted: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0
    sources_blocked: int = 0
    widen_rounds: int = 0
    elapsed_s: float = 0.0
    per_source: list = field(default_factory=list)   # [SourceResult, ...]
    jobs: list = field(default_factory=list)         # deduped RawJob[] for the caller
