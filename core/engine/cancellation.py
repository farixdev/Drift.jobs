"""Cooperative cancellation — Python's answer to AbortController.

A `CancelToken` wraps a threading.Event. Long loops and the fetch layer check it
between requests; per-request timeouts bound anything already in flight (requests
can't hard-abort a socket mid-read without extra machinery, so timeout + between-
request checks is the clean, correct approach).
"""
from __future__ import annotations

import threading


class Cancelled(Exception):
    """Raised by `check()` when a run has been cancelled."""


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()

    def wait(self, timeout: float) -> bool:
        """Sleep up to `timeout`, returning True if cancelled during the wait."""
        return self._event.wait(timeout)
