"""Per-run token budget with a hard stop and an 80% warning.

The manager checks `allow()` before each call and records tokens after. When the
budget is exhausted the next call raises BudgetExceededError rather than spending
past the ceiling. A budget of 0/None means unlimited.
"""
from __future__ import annotations

from typing import Callable

from core.ai.errors import BudgetExceededError
from core.ai.types import Usage


class TokenBudget:
    def __init__(self, limit: int | None, on_warn: Callable[[int, int], None] | None = None):
        self.limit = limit or 0            # 0 = unlimited
        self.spent = 0
        self._on_warn = on_warn
        self._warned = False

    @property
    def unlimited(self) -> bool:
        return self.limit <= 0

    def remaining(self) -> int:
        if self.unlimited:
            return 10 ** 12
        return max(0, self.limit - self.spent)

    def allow(self) -> None:
        """Raise if the budget is already spent. Called before each LLM call."""
        if not self.unlimited and self.spent >= self.limit:
            raise BudgetExceededError(
                f"per-run token budget of {self.limit:,} reached")

    def add(self, usage: Usage) -> None:
        self.spent += usage.total_tokens
        if (not self.unlimited and not self._warned
                and self.spent >= 0.8 * self.limit):
            self._warned = True
            if self._on_warn:
                self._on_warn(self.spent, self.limit)

    def fraction(self) -> float:
        if self.unlimited:
            return 0.0
        return min(1.0, self.spent / self.limit)
