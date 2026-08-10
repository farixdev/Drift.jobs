"""Run configuration for the execution engine.

Loaded from the `engine.config` setting, overlaid on defaults, and clamped to
safe ranges. The UI (Phase 10 Settings) edits these; nothing here is hardcoded
beyond the documented defaults.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class RunConfig:
    global_concurrency: int = 12       # 1..64
    per_domain_concurrency: int = 4    # independent per-domain cap
    source_timeout_s: int = 30         # per-source wall clock
    run_timeout_s: int = 600           # per-run; up to 3600
    max_retries: int = 3               # per HTTP call, retryable classes only
    min_results: int = 0               # 0 = never widen
    max_results: int = 0               # 0 = no hard cap
    max_widen_rounds: int = 2
    proxy: str = ""                    # user-supplied; off by default
    widen: bool = True

    def clamped(self) -> "RunConfig":
        return RunConfig(
            global_concurrency=_clamp(self.global_concurrency, 1, 64),
            per_domain_concurrency=_clamp(self.per_domain_concurrency, 1, 16),
            source_timeout_s=_clamp(self.source_timeout_s, 5, 300),
            run_timeout_s=_clamp(self.run_timeout_s, 30, 3600),
            max_retries=_clamp(self.max_retries, 0, 6),
            min_results=max(0, self.min_results),
            max_results=max(0, self.max_results),
            max_widen_rounds=_clamp(self.max_widen_rounds, 0, 5),
            proxy=self.proxy or "",
            widen=bool(self.widen),
        )

    @classmethod
    def load(cls) -> "RunConfig":
        try:
            from db import get_setting
            data = get_setting("engine.config", {}) or {}
        except Exception:
            data = {}
        base = asdict(cls())
        base.update({k: v for k, v in data.items() if k in base})
        return cls(**base).clamped()

    def save(self) -> None:
        from db import set_setting
        set_setting("engine.config", asdict(self.clamped()))


def _clamp(v: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo
