"""OpenAI-compatible provider — one class parameterised by the registry spec.

Serves OpenAI, Groq, OpenRouter, Mistral, DeepSeek, and Ollama: all speak the
`/chat/completions`, `/embeddings`, and `/models` shapes. The only variation is
the auth header, which comes from the spec's `auth_style`.
"""
from __future__ import annotations

from collections.abc import Iterator

from core.ai import http
from core.ai.base import LLMProvider
from core.ai.errors import BadResponseError
from core.ai.types import CompletionResult, EmbeddingResult, Message, ModelInfo, Usage


class OpenAICompatProvider(LLMProvider):
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.spec.auth_style == "bearer":
            h["Authorization"] = f"Bearer {self._key()}"
        if self.spec.slug == "openrouter":
            # OpenRouter asks callers to identify their app; honest + non-PII.
            h["HTTP-Referer"] = "https://github.com/farixdev/Drift-JobFinder"
            h["X-Title"] = "Drift"
        return h

    def _chat(self, messages, model, *, temperature, max_tokens, json_mode) -> CompletionResult:
        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = http.request(self.spec, "POST", f"{self.spec.base_url}/chat/completions",
                            headers=self._headers(), json_body=body, key=self._key_or_blank())
        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise BadResponseError(f"unexpected chat response shape: {exc}",
                                   provider=self.slug) from exc
        usage = _usage(data.get("usage"))
        return CompletionResult(text=text.strip(), usage=usage, model=model, provider=self.slug)

    def _stream(self, messages, model, *, temperature, max_tokens) -> Iterator[str]:
        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        resp = http.request(self.spec, "POST", f"{self.spec.base_url}/chat/completions",
                            headers=self._headers(), json_body=body,
                            key=self._key_or_blank(), stream=True)
        import json as _json
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = _json.loads(payload)
                delta = chunk["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield delta
            except (KeyError, IndexError, ValueError):
                continue

    def _embed(self, texts, model) -> EmbeddingResult:
        body = {"model": model, "input": texts}
        resp = http.request(self.spec, "POST", f"{self.spec.base_url}/embeddings",
                            headers=self._headers(), json_body=body, key=self._key_or_blank())
        data = resp.json()
        try:
            vectors = [row["embedding"] for row in data["data"]]
        except (KeyError, TypeError) as exc:
            raise BadResponseError(f"unexpected embeddings shape: {exc}",
                                   provider=self.slug) from exc
        return EmbeddingResult(vectors=vectors, usage=_usage(data.get("usage")),
                               model=model, provider=self.slug)

    def _list_models(self) -> list[ModelInfo]:
        resp = http.request(self.spec, "GET", self.spec.models_url,
                            headers=self._headers(), key=self._key_or_blank())
        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else data
        out: list[ModelInfo] = []
        for it in items or []:
            mid = it.get("id") if isinstance(it, dict) else None
            if mid:
                out.append(ModelInfo(id=mid, provider=self.slug,
                                     supports_embeddings=self.spec.supports_embeddings))
        return out

    def _key_or_blank(self) -> str:
        """Key for redaction/auth; blank for keyless providers (Ollama)."""
        return self._key() if self.spec.needs_key else ""


def _usage(u: dict | None) -> Usage:
    if not isinstance(u, dict):
        return Usage()
    return Usage(prompt_tokens=int(u.get("prompt_tokens") or 0),
                 completion_tokens=int(u.get("completion_tokens") or 0))
