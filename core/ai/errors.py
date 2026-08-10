"""Typed provider errors — with hard guarantees that a key never leaks.

Every error raised out of the AI layer passes its message through `redact()`,
so an API key can never reach a log line, a UI toast, a telemetry payload, or an
exported file (Phase 3 hard constraint). `redact()` is applied at construction,
not at print time, so even an error that is stored or re-raised stays clean.
"""
from __future__ import annotations

import re

# Key-shaped tokens to scrub even when we don't hold the literal string:
# sk-..., gsk_..., Google AIza..., Bearer <token>, and long opaque hex/b64 runs.
_KEY_PATTERNS = [
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9._\-]{12,}"),
    re.compile(r"gsk_[A-Za-z0-9]{12,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(api[_-]?key\"?\s*[:=]\s*\"?)[^\s\"',}]{12,}"),
]


def redact(text: str, *literals: str) -> str:
    """Scrub any known literal secret and any key-shaped token from `text`."""
    if not text:
        return text
    out = str(text)
    for lit in literals:
        if lit and len(lit) >= 6:
            out = out.replace(lit, "***")
    for pat in _KEY_PATTERNS:
        out = pat.sub("***", out)
    return out


class ProviderError(Exception):
    """Base class. `message` is already redacted; `retryable` drives backoff."""

    retryable: bool = False

    def __init__(self, message: str, *, provider: str = "", status: int | None = None,
                 secrets: tuple[str, ...] = ()):
        self.provider = provider
        self.status = status
        clean = redact(message, *secrets)
        super().__init__(clean)


class AuthError(ProviderError):
    """401/403 — bad or missing key. Never retried, never walked-past silently."""
    retryable = False


class RateLimitError(ProviderError):
    """429. Retried with backoff; honours Retry-After when present."""
    retryable = True

    def __init__(self, message: str, *, retry_after: float | None = None, **kw):
        self.retry_after = retry_after
        super().__init__(message, **kw)


class ServerError(ProviderError):
    """5xx — transient upstream failure. Retryable."""
    retryable = True


class TimeoutError_(ProviderError):
    """Network timeout. Retryable."""
    retryable = True


class BadResponseError(ProviderError):
    """2xx but unparseable / schema-invalid after the repair retry. Not retryable."""
    retryable = False


class HostMismatchError(ProviderError):
    """A request was about to go to a host that isn't the provider's registered
    domain. Hard stop — a key must only ever transit to its own provider."""
    retryable = False


class NoKeyError(ProviderError):
    """No key configured for a provider that requires one."""
    retryable = False


class BudgetExceededError(ProviderError):
    """The per-run token budget hard stop was hit."""
    retryable = False
