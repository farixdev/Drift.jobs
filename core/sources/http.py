"""Honest HTTP for sources, with retry, rate limiting, and cancellation.

One real, identifiable User-Agent (no browser spoofing, no evasion). Retries only
retryable classes (429, 5xx, network timeout) with exponential backoff + full
jitter, honouring Retry-After; 4xx auth/404 fail immediately. A `DomainLimiter`
paces requests per host; a `CancelToken` aborts between attempts. Returns a
structured `Fetch` so callers surface status/error class rather than swallowing.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import requests

USER_AGENT = "drift-jobfinder/3.0 (+https://github.com/farixdev/Drift-JobFinder)"
DEFAULT_TIMEOUT = 25
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_BASE_BACKOFF = 0.8
_MAX_BACKOFF = 20.0


@dataclass
class Fetch:
    ok: bool
    status: int | None
    json: Any = None
    text: str = ""
    error_class: str = ""
    error_detail: str = ""
    attempts: int = 1


def get(spec_url: str, *, method: str = "GET", headers: dict | None = None,
        params: dict | None = None, json_body: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT, want_json: bool = True,
        retries: int = 0, limiter=None, cancel=None, proxy: str = "") -> Fetch:
    hdrs = dict(_HEADERS)
    if headers:
        hdrs.update(headers)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    attempt = 0
    while True:
        if cancel is not None and getattr(cancel, "cancelled", False):
            return Fetch(ok=False, status=None, error_class="Cancelled",
                         error_detail="run cancelled", attempts=attempt + 1)
        try:
            if limiter is not None:
                with limiter.slot(spec_url, cancel):
                    resp = requests.request(method, spec_url, headers=hdrs, params=params,
                                            json=json_body, timeout=timeout, proxies=proxies)
            else:
                resp = requests.request(method, spec_url, headers=hdrs, params=params,
                                        json=json_body, timeout=timeout, proxies=proxies)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt < retries:
                _sleep(_backoff(attempt), cancel)
                attempt += 1
                continue
            return Fetch(ok=False, status=None, error_class=type(exc).__name__,
                         error_detail=str(exc)[:200], attempts=attempt + 1)
        except requests.RequestException as exc:
            return Fetch(ok=False, status=None, error_class=type(exc).__name__,
                         error_detail=str(exc)[:200], attempts=attempt + 1)

        if resp.status_code >= 400:
            if resp.status_code in _RETRYABLE_STATUS and attempt < retries:
                _sleep(_backoff(attempt, _retry_after(resp)), cancel)
                attempt += 1
                continue
            return Fetch(ok=False, status=resp.status_code,
                         error_class=f"HTTP{resp.status_code}",
                         error_detail=(resp.text or "")[:200], attempts=attempt + 1)

        if want_json:
            try:
                return Fetch(ok=True, status=resp.status_code, json=resp.json(),
                             attempts=attempt + 1)
            except ValueError as exc:
                return Fetch(ok=False, status=resp.status_code, error_class="BadJSON",
                             error_detail=str(exc)[:120], attempts=attempt + 1)
        return Fetch(ok=True, status=resp.status_code, text=resp.text, attempts=attempt + 1)


def _retry_after(resp) -> float | None:
    val = resp.headers.get("Retry-After")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _backoff(attempt: int, retry_after: float | None = None) -> float:
    ceiling = min(_MAX_BACKOFF, _BASE_BACKOFF * (2 ** attempt))
    jitter = random.uniform(0, ceiling)  # full jitter
    return max(retry_after, jitter) if retry_after is not None else jitter


def _sleep(seconds: float, cancel) -> None:
    if cancel is not None:
        cancel.wait(seconds)  # wake early if cancelled
    else:
        time.sleep(seconds)
