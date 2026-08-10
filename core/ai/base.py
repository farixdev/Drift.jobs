"""LLMProvider — the single interface every provider implements.

Public methods (`complete`, `complete_structured`, `stream`, `embed`,
`list_models`, `test_connection`, `estimate_cost`) live here and wrap four
provider-specific primitives (`_chat`, `_stream`, `_embed`, `_list_models`), so
each adapter stays small and the cross-cutting behaviour — timing, error
redaction, the JSON-schema repair loop — is written once.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator

from core.ai import jsonutil
from core.ai.errors import BadResponseError, NoKeyError
from core.ai.keystore import KeyStore, default_store
from core.ai.models_fallback import fallback_models
from core.ai.registry import ProviderSpec
from core.ai.types import (
    CompletionResult,
    ConnectionStatus,
    EmbeddingResult,
    Message,
    ModelInfo,
    Usage,
)


class LLMProvider(ABC):
    def __init__(self, spec: ProviderSpec, keystore: KeyStore | None = None):
        self.spec = spec
        self._keys = keystore or default_store()

    # -- key access -------------------------------------------------------- #
    @property
    def slug(self) -> str:
        return self.spec.slug

    def _key(self) -> str:
        if not self.spec.needs_key:
            return ""
        key = self._keys.get_key(self.spec.slug)
        if not key:
            raise NoKeyError(f"no API key configured for {self.spec.display_name}",
                             provider=self.spec.slug)
        return key

    def has_key(self) -> bool:
        return not self.spec.needs_key or self._keys.has_key(self.spec.slug)

    # -- primitives (implemented per provider) ----------------------------- #
    @abstractmethod
    def _chat(self, messages: list[Message], model: str, *, temperature: float,
              max_tokens: int, json_mode: bool) -> CompletionResult: ...

    @abstractmethod
    def _stream(self, messages: list[Message], model: str, *, temperature: float,
                max_tokens: int) -> Iterator[str]: ...

    @abstractmethod
    def _embed(self, texts: list[str], model: str) -> EmbeddingResult: ...

    @abstractmethod
    def _list_models(self) -> list[ModelInfo]: ...

    # -- public API -------------------------------------------------------- #
    def complete(self, messages: list[Message], model: str, *,
                 temperature: float = 0.2, max_tokens: int = 1024,
                 json_mode: bool = False, task: str = "") -> CompletionResult:
        t0 = time.time()
        result = self._chat(messages, model, temperature=temperature,
                            max_tokens=max_tokens, json_mode=json_mode)
        result.latency_ms = int((time.time() - t0) * 1000)
        result.task = task
        return result

    def complete_structured(self, messages: list[Message], schema: dict, model: str, *,
                            temperature: float = 0.1, max_tokens: int = 1024,
                            task: str = "", repair: bool = True) -> tuple[object, CompletionResult]:
        """Return (parsed_object, result). Parse + schema-validate; on failure do
        exactly one repair retry that feeds the errors back, then hard-fail.
        Never silently accepts malformed JSON (Phase 3 hard constraint)."""
        result = self.complete(messages, model, temperature=temperature,
                               max_tokens=max_tokens, json_mode=True, task=task)
        obj, errors = self._parse_and_validate(result.text, schema)
        if not errors:
            return obj, result

        if not repair:
            raise BadResponseError(
                f"structured output invalid: {'; '.join(errors[:4])}",
                provider=self.slug)

        repair_msg = Message("user", (
            "Your previous reply did not match the required JSON schema. "
            f"Errors: {'; '.join(errors[:6])}. "
            "Return ONLY corrected JSON that satisfies the schema — no prose, no fences."
        ))
        retry = self.complete(messages + [Message("assistant", result.text), repair_msg],
                              model, temperature=0.0, max_tokens=max_tokens,
                              json_mode=True, task=task)
        # Roll the repair's token cost into the reported usage.
        retry.usage = retry.usage + result.usage
        obj, errors = self._parse_and_validate(retry.text, schema)
        if errors:
            raise BadResponseError(
                f"structured output still invalid after repair: {'; '.join(errors[:4])}",
                provider=self.slug)
        return obj, retry

    @staticmethod
    def _parse_and_validate(text: str, schema: dict) -> tuple[object, list[str]]:
        try:
            obj = jsonutil.extract_json(text)
        except json.JSONDecodeError as exc:
            return None, [f"not valid JSON: {exc.msg}"]
        return obj, jsonutil.validate(obj, schema)

    def stream(self, messages: list[Message], model: str, *,
               temperature: float = 0.2, max_tokens: int = 1024) -> Iterator[str]:
        return self._stream(messages, model, temperature=temperature, max_tokens=max_tokens)

    def embed(self, texts: list[str], model: str) -> EmbeddingResult:
        if not self.spec.supports_embeddings:
            raise BadResponseError(f"{self.spec.display_name} does not offer embeddings",
                                   provider=self.slug)
        return self._embed(texts, model)

    def list_models(self) -> list[ModelInfo]:
        """Live model list; falls back to the dated constant on any failure."""
        try:
            models = self._list_models()
            if models:
                return models
        except Exception:
            pass
        return [ModelInfo(id=m, provider=self.slug) for m in fallback_models(self.slug)]

    def test_connection(self) -> ConnectionStatus:
        from core.ai.errors import redact
        t0 = time.time()
        try:
            models = self._list_models()
            return ConnectionStatus(ok=True, latency_ms=int((time.time() - t0) * 1000),
                                    models=[m.id for m in models])
        except Exception as exc:
            return ConnectionStatus(ok=False, latency_ms=int((time.time() - t0) * 1000),
                                    detail=redact(str(exc)))

    def estimate_cost(self, usage: Usage, model: str) -> float:
        from core.ai.cost import estimate_cost
        return estimate_cost(self.slug, model, usage)
