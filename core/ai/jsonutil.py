"""JSON extraction + a minimal JSON-Schema validator.

The full `jsonschema` package would be heavier than we need and a new dependency;
our structured tasks use a small subset (object/array/string/number/integer/
boolean, `required`, `properties`, `items`). `validate()` covers exactly that and
returns a list of human-readable errors, which the repair retry feeds back to the
model. If a task ever needs full draft-2020 validation, swapping in `jsonschema`
is a one-function change.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)


def extract_json(text: str) -> Any:
    """Parse JSON from a model response, tolerating ``` fences and leading prose.

    Raises json.JSONDecodeError if nothing parseable is found.
    """
    s = (text or "").strip()
    if s.startswith("```"):
        s = _FENCE.sub("", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced {...} or [...] span.
    start = min((i for i in (s.find("{"), s.find("[")) if i != -1), default=-1)
    if start == -1:
        raise json.JSONDecodeError("no JSON found", s, 0)
    opener = s[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    return json.loads(s[start : i + 1])
    raise json.JSONDecodeError("unbalanced JSON", s, start)


_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def validate(obj: Any, schema: dict, path: str = "$") -> list[str]:
    """Return a list of validation errors ([] means valid)."""
    errors: list[str] = []
    typ = schema.get("type")
    if typ and typ in _TYPE_CHECKS and not _TYPE_CHECKS[typ](obj):
        errors.append(f"{path}: expected {typ}, got {type(obj).__name__}")
        return errors  # further checks are meaningless on a type mismatch

    if typ == "object":
        for req in schema.get("required", []):
            if req not in obj:
                errors.append(f"{path}: missing required key '{req}'")
        for key, subschema in (schema.get("properties") or {}).items():
            if key in obj:
                errors.extend(validate(obj[key], subschema, f"{path}.{key}"))
    elif typ == "array":
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(obj):
                errors.extend(validate(item, item_schema, f"{path}[{i}]"))
    return errors
