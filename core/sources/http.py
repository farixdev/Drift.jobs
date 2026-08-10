"""Honest HTTP for sources.

One real, current, honest User-Agent (no browser spoofing, no evasion). Returns a
structured `Fetch` so the caller can surface the HTTP status and error class
instead of swallowing failures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

# Honest, identifiable UA — Compliance §UA. Never impersonates a browser.
USER_AGENT = "drift-jobfinder/3.0 (+https://github.com/farixdev/Drift-JobFinder)"
DEFAULT_TIMEOUT = 25

_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


@dataclass
class Fetch:
    ok: bool
    status: int | None
    json: Any = None
    text: str = ""
    error_class: str = ""
    error_detail: str = ""


def get(spec_url: str, *, method: str = "GET", headers: dict | None = None,
        params: dict | None = None, json_body: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT, want_json: bool = True) -> Fetch:
    hdrs = dict(_HEADERS)
    if headers:
        hdrs.update(headers)
    try:
        resp = requests.request(method, spec_url, headers=hdrs, params=params,
                                json=json_body, timeout=timeout)
    except requests.RequestException as exc:
        return Fetch(ok=False, status=None, error_class=type(exc).__name__,
                     error_detail=str(exc)[:200])
    if resp.status_code >= 400:
        return Fetch(ok=False, status=resp.status_code,
                     error_class=f"HTTP{resp.status_code}",
                     error_detail=(resp.text or "")[:200])
    if want_json:
        try:
            return Fetch(ok=True, status=resp.status_code, json=resp.json())
        except ValueError as exc:
            return Fetch(ok=False, status=resp.status_code, error_class="BadJSON",
                         error_detail=str(exc)[:120])
    return Fetch(ok=True, status=resp.status_code, text=resp.text)
