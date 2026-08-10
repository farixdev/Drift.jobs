"""Native (non-OpenAI-shaped) providers: Anthropic Messages, Google Gemini.

Both keep keys out of the URL — Anthropic uses `x-api-key`, Gemini uses
`x-goog-api-key` — so a key is never placed in a query string.
"""
from __future__ import annotations

import json as _json
from collections.abc import Iterator

from core.ai import http
from core.ai.base import LLMProvider
from core.ai.errors import BadResponseError
from core.ai.types import CompletionResult, EmbeddingResult, Message, ModelInfo, Usage

_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    def _headers(self) -> dict:
        return {
            "x-api-key": self._key(),
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _split(messages: list[Message]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [{"role": m.role, "content": m.content}
                 for m in messages if m.role in ("user", "assistant")]
        return system, turns

    def _chat(self, messages, model, *, temperature, max_tokens, json_mode) -> CompletionResult:
        system, turns = self._split(messages)
        if json_mode:
            system = (system + "\n\n" if system else "") + \
                "Respond with a single valid JSON value only — no prose, no code fences."
        body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": turns}
        if system:
            body["system"] = system
        resp = http.request(self.spec, "POST", f"{self.spec.base_url}/messages",
                            headers=self._headers(), json_body=body, key=self._key())
        data = resp.json()
        try:
            parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
            text = "".join(parts)
        except (KeyError, TypeError, AttributeError) as exc:
            raise BadResponseError(f"unexpected messages shape: {exc}", provider=self.slug) from exc
        u = data.get("usage") or {}
        usage = Usage(prompt_tokens=int(u.get("input_tokens") or 0),
                      completion_tokens=int(u.get("output_tokens") or 0))
        return CompletionResult(text=text.strip(), usage=usage, model=model, provider=self.slug)

    def _stream(self, messages, model, *, temperature, max_tokens) -> Iterator[str]:
        system, turns = self._split(messages)
        body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": turns, "stream": True}
        if system:
            body["system"] = system
        resp = http.request(self.spec, "POST", f"{self.spec.base_url}/messages",
                            headers=self._headers(), json_body=body, key=self._key(), stream=True)
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            try:
                event = _json.loads(line[5:].strip())
            except ValueError:
                continue
            if event.get("type") == "content_block_delta":
                delta = event.get("delta", {}).get("text")
                if delta:
                    yield delta

    def _embed(self, texts, model) -> EmbeddingResult:  # pragma: no cover - guarded by base
        raise BadResponseError("Anthropic does not offer embeddings", provider=self.slug)

    def _list_models(self) -> list[ModelInfo]:
        resp = http.request(self.spec, "GET", self.spec.models_url,
                            headers=self._headers(), key=self._key())
        data = resp.json()
        return [ModelInfo(id=it["id"], provider=self.slug)
                for it in data.get("data", []) if it.get("id")]


class GeminiProvider(LLMProvider):
    def _headers(self) -> dict:
        return {"x-goog-api-key": self._key(), "Content-Type": "application/json",
                "Accept": "application/json"}

    @staticmethod
    def _model_id(model: str) -> str:
        return model[len("models/"):] if model.startswith("models/") else model

    def _chat(self, messages, model, *, temperature, max_tokens, json_mode) -> CompletionResult:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        contents = [{"role": "model" if m.role == "assistant" else "user",
                     "parts": [{"text": m.content}]}
                    for m in messages if m.role in ("user", "assistant")]
        gen_cfg = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        body: dict = {"contents": contents, "generationConfig": gen_cfg}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self.spec.base_url}/models/{self._model_id(model)}:generateContent"
        resp = http.request(self.spec, "POST", url, headers=self._headers(),
                            json_body=body, key=self._key())
        data = resp.json()
        try:
            cand = data["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"])
        except (KeyError, IndexError, TypeError) as exc:
            raise BadResponseError(f"unexpected generateContent shape: {exc}",
                                   provider=self.slug) from exc
        um = data.get("usageMetadata") or {}
        usage = Usage(prompt_tokens=int(um.get("promptTokenCount") or 0),
                      completion_tokens=int(um.get("candidatesTokenCount") or 0))
        return CompletionResult(text=text.strip(), usage=usage, model=model, provider=self.slug)

    def _stream(self, messages, model, *, temperature, max_tokens) -> Iterator[str]:
        # Non-streaming fallback: yield the whole completion once. Keeps the
        # public stream() contract without a second code path to maintain.
        yield self._chat(messages, model, temperature=temperature,
                         max_tokens=max_tokens, json_mode=False).text

    def _embed(self, texts, model) -> EmbeddingResult:
        mid = self._model_id(model)
        reqs = [{"model": f"models/{mid}", "content": {"parts": [{"text": t}]}} for t in texts]
        url = f"{self.spec.base_url}/models/{mid}:batchEmbedContents"
        resp = http.request(self.spec, "POST", url, headers=self._headers(),
                            json_body={"requests": reqs}, key=self._key())
        data = resp.json()
        try:
            vectors = [e["values"] for e in data["embeddings"]]
        except (KeyError, TypeError) as exc:
            raise BadResponseError(f"unexpected embeddings shape: {exc}",
                                   provider=self.slug) from exc
        return EmbeddingResult(vectors=vectors, usage=Usage(), model=model, provider=self.slug)

    def _list_models(self) -> list[ModelInfo]:
        resp = http.request(self.spec, "GET", self.spec.models_url,
                            headers=self._headers(), key=self._key())
        data = resp.json()
        out: list[ModelInfo] = []
        for it in data.get("models", []):
            name = it.get("name", "")
            mid = name[len("models/"):] if name.startswith("models/") else name
            if mid:
                out.append(ModelInfo(id=mid, provider=self.slug,
                                     context_window=it.get("inputTokenLimit")))
        return out
