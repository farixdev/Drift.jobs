"""Search criteria layer (Phase 5): the full query object, its filter, and saved
searches.

    from core.search import apply_criteria, save_search, list_searches, get_search
"""
from core.search.filter import apply_criteria
from core.search.store import (
    delete_search,
    duplicate_search,
    get_search,
    list_searches,
    mark_run,
    save_search,
    set_active,
)
from core.sources.spec import SearchCriteria

# Controlled-vocabulary option lists for the builder UI.
SENIORITY_OPTIONS = ["intern", "junior", "mid", "senior", "principal"]
EMPLOYMENT_OPTIONS = ["full_time", "part_time", "contract", "freelance",
                      "internship", "temporary"]
LOCATION_MODES = ["any", "remote", "hybrid", "onsite"]
FRESHNESS_OPTIONS = [(None, "Any time"), (1, "24 hours"), (3, "3 days"),
                     (7, "7 days"), (14, "14 days"), (30, "30 days")]

__all__ = [
    "SearchCriteria", "apply_criteria", "save_search", "list_searches",
    "get_search", "duplicate_search", "delete_search", "mark_run", "set_active",
    "SENIORITY_OPTIONS", "EMPLOYMENT_OPTIONS", "LOCATION_MODES", "FRESHNESS_OPTIONS",
]
