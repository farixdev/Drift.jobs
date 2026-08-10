"""Per-domain token-bucket rate limiting + concurrency caps.

Each domain gets a token bucket sized from the source's declared `rate_limit_rpm`
and a semaphore for the per-domain concurrency cap. The fetch layer acquires a
`slot(url)` — one token + one concurrency permit — before every request, so two
sources sharing a host still respect a single domain budget.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from urllib.parse import urlparse


class TokenBucket:
    def __init__(self, rpm: float, burst: int | None = None):
        self.rate = max(rpm, 1) / 60.0                      # tokens per second
        self.capacity = burst if burst is not None else max(1, int(rpm // 6) or 1)
        self._tokens = float(self.capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, cancel=None) -> bool:
        """Block until a token is available. Returns False if cancelled."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return True
                wait = (1 - self._tokens) / self.rate
            if cancel is not None and getattr(cancel, "cancelled", False):
                return False
            time.sleep(min(wait, 0.1))


class DomainLimiter:
    def __init__(self, default_rpm: int = 120, per_domain_concurrency: int = 4):
        self._default_rpm = default_rpm
        self._conc = per_domain_concurrency
        self._buckets: dict[str, TokenBucket] = {}
        self._sems: dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def configure(self, url: str, rpm: int) -> None:
        host = urlparse(url).netloc.lower()
        with self._lock:
            if host not in self._buckets:
                self._buckets[host] = TokenBucket(rpm or self._default_rpm)
                self._sems[host] = threading.Semaphore(self._conc)

    def _for(self, host: str):
        with self._lock:
            if host not in self._buckets:
                self._buckets[host] = TokenBucket(self._default_rpm)
                self._sems[host] = threading.Semaphore(self._conc)
            return self._buckets[host], self._sems[host]

    @contextmanager
    def slot(self, url: str, cancel=None):
        host = urlparse(url).netloc.lower()
        bucket, sem = self._for(host)
        bucket.acquire(cancel)
        sem.acquire()
        try:
            yield
        finally:
            sem.release()
