"""Declarative source registry (Phase 6).

Sources are data: each `SourceDefinition` lives in `definitions/` and is loaded
here. The engine (`run_source`) is source-agnostic. Adding a source never
requires touching engine code.
"""
from core.sources.definitions import ALL
from core.sources.runner import run_source
from core.sources.spec import (
    RequestSpec,
    SearchCriteria,
    SourceDefinition,
    SourceResult,
)

DEFINITIONS: dict[str, SourceDefinition] = {d.slug: d for d in ALL}


def get_definition(slug: str) -> SourceDefinition:
    return DEFINITIONS[slug]


def all_definitions() -> list[SourceDefinition]:
    return list(ALL)


def enabled_definitions() -> list[SourceDefinition]:
    return [d for d in ALL if d.enabled]


__all__ = [
    "DEFINITIONS", "get_definition", "all_definitions", "enabled_definitions",
    "run_source", "SearchCriteria", "SourceDefinition", "SourceResult", "RequestSpec",
]
