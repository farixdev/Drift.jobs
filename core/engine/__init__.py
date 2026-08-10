"""Drift concurrent execution engine (Phase 7).

    from core.engine import ScanEngine, RunConfig, CancelToken
    engine = ScanEngine(RunConfig.load(), on_event=handler, cancel=token)
    summary = engine.run(enabled_definitions(), criteria)
    jobs = summary.jobs
"""
from core.engine import events
from core.engine.cancellation import CancelToken, Cancelled
from core.engine.config import RunConfig
from core.engine.engine import ScanEngine
from core.engine.events import RunEvent, RunSummary

__all__ = ["ScanEngine", "RunConfig", "CancelToken", "Cancelled",
           "RunEvent", "RunSummary", "events"]
