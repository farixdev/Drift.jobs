"""Bridge a declarative SourceDefinition to the legacy BaseScraper interface.

Lets the current worker run the new ATS sources unchanged: `.search()` maps the
legacy (keywords, location) call onto a SearchCriteria, runs the source, stashes
the full `SourceResult` on `last_result` (so the worker can surface HTTP status /
error class / timestamp), and returns the jobs. Phase 7's engine will call
`run_source` directly and retire this shim.
"""
from __future__ import annotations

from core.scraper.base import BaseScraper, RawJob
from core.sources.runner import run_source
from core.sources.spec import SearchCriteria, SourceDefinition


class DeclarativeScraper(BaseScraper):
    def __init__(self, definition: SourceDefinition):
        self.definition = definition
        self.label = definition.display_name
        self.recommended = True
        self.needs_browser = definition.adapter_type == "browser"
        self.last_result = None

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        criteria = SearchCriteria.from_legacy(keywords, location)
        result = run_source(self.definition, criteria)
        self.last_result = result
        return result.jobs
