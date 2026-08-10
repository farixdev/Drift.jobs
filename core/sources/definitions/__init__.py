"""Auto-loaded source definitions.

Every module here exposes a `DEFINITION`. The registry imports `ALL` — adding a
source means adding a module + listing it here, never touching engine code.
"""
from core.sources.definitions import (
    ashby,
    greenhouse,
    himalayas,
    lever,
    workable,
    workingnomads,
)

ALL = [
    greenhouse.DEFINITION,
    lever.DEFINITION,
    ashby.DEFINITION,
    workable.DEFINITION,
    himalayas.DEFINITION,
    workingnomads.DEFINITION,
]
