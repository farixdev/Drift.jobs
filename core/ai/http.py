"""Shared HTTP layer for providers: host assertion + retry with jittered backoff.

Two guarantees live here:
1. **Host assertion.** Before any request goes out, the target host is checked
   against the provider's registered host. A mismatch is a hard stop — a key must
   only ever transit to its own provider (Phase 3 key-safety rule).
2. **Retry policy.** Retryable failures (429, 5xx, network timeout) back off
   exponentially with full jitter and honour `Retry-After`. Non-retryable
   failures (401/403 auth, other 4xx) raise immediately — never retried, never
   swallowed.

The retry loop calls an injectable `sleep`; tests pass a no-op to run instantly.
"""
from __future__ import annotations

import random
import time
from typing import Callable
from urllib.parse import urlparse

import requests

from core.ai.errors import (
    AuthError,
    BadResponseError,
    HostMismatchError,
    RateLimitError,
    ServerError,
    TimeoutError_,
)
from core.ai.registry import ProviderSpec

DEFAULT_TIMEOUT = 45
MAX_RETRIES = 3
_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


def _retry_after_seconds(resp: requests.Response) -> float | None:
    val = resp.headers.get("Retry-After")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def request(
    spec: ProviderSpec,
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    json_body: dict | None = None,
    key: str = "",
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
    stream: bool = False,
) -> requests.Response:
    """Perform an HTTP request with host assertion + retry. Returns a 2xx response
    or raises a typed ProviderError (message already redacted of `key`)."""
    host = urlparse(url).netloc.lower()
    if host != spec.host:
        raise HostMismatchError(
            f"refusing to send {spec.slug} request to {host!r}; "
            f"registered host is {spec.host!r}",
            provider=spec.slug, secrets=(key,),
        )

    attempt = 0
    while True:
        try:
            resp = requests.request(
                method, url, headers=headers, json=json_body,
                timeout=timeout, stream=stream,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt >= max_retries:
                raise TimeoutError_(f"network error: {exc}", provider=spec.slug,
                                    secrets=(key,)) from exc
            sleep(_backoff(attempt))
            attempt += 1
            continue

        if resp.status_code < 400:
            return resp

        body = _safe_body(resp)
        if resp.status_code in (401, 403):
            raise AuthError(f"auth failed ({resp.status_code}): {body}",
                            provider=spec.slug, status=resp.status_code, secrets=(key,))
        if resp.status_code == 429:
            if attempt >= max_retries:
                raise RateLimitError(f"rate limited: {body}", provider=spec.slug,
                                     status=429, secrets=(key,))
            sleep(_backoff(attempt, _retry_after_seconds(resp)))
            attempt += 1
            continue
        if resp.status_code >= 500:
            if attempt >= max_retries:
                raise ServerError(f"server error ({resp.status_code}): {body}",
                                  provider=spec.slug, status=resp.status_code, secrets=(key,))
            sleep(_backoff(attempt))
            attempt += 1
            continue
        # Other 4xx: caller sent something wrong. Do not retry.
        raise BadResponseError(f"request rejected ({resp.status_code}): {body}",
                               provider=spec.slug, status=resp.status_code, secrets=(key,))


def _backoff(attempt: int, retry_after: float | None = None) -> float:
    ceiling = min(_MAX_BACKOFF, _BASE_BACKOFF * (2 ** attempt))
    jittered = random.uniform(0, ceiling)  # full jitter
    if retry_after is not None:
        return max(retry_after, jittered)
    return jittered


def _safe_body(resp: requests.Response) -> str:
    try:
        return resp.text[:300]
    except Exception:
        return "<unreadable body>"
