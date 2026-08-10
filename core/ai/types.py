"""Shared value types for the AI layer. Provider-agnostic by design."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.prompt_tokens + other.prompt_tokens,
                     self.completion_tokens + other.completion_tokens)


@dataclass
class CompletionResult:
    text: str
    usage: Usage
    model: str
    provider: str
    # Which task requested this, and whether it came from cache / a fallback hop.
    task: str = ""
    from_cache: bool = False
    fallback_depth: int = 0
    latency_ms: int = 0

    def label(self) -> str:
        """Human string for 'which model served this', shown on result surfaces."""
        tag = f"{self.provider}:{self.model}"
        if self.from_cache:
            tag += " (cached)"
        elif self.fallback_depth:
            tag += f" (fallback #{self.fallback_depth})"
        return tag


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    usage: Usage
    model: str
    provider: str


@dataclass
class ModelInfo:
    id: str
    provider: str
    # Populated only when the provider advertises it; never invented.
    context_window: int | None = None
    supports_embeddings: bool = False


@dataclass
class ConnectionStatus:
    ok: bool
    latency_ms: int
    models: list[str] = field(default_factory=list)
    detail: str = ""  # redacted error text when ok is False
