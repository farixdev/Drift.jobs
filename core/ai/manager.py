"""LLMManager — the one entry point the rest of the app calls.

Ties routing, fallback, cache, cost, and budget together:

  run_task(task, messages)            -> CompletionResult
  run_structured(task, messages, schema) -> (obj, CompletionResult)
  embed_task(task, texts)             -> EmbeddingResult

For each call it resolves the task's route, then walks the primary→fallback chain.
Per-call retry/backoff lives in the HTTP layer; the manager walks to the NEXT
provider only on a retryable failure that survived retries, or a missing key.
Auth errors on the primary still try the fallback (the fallback may have a key
the primary lacks). Every attempt is logged to the usage ledger with its cost,
and the served model is stamped onto the result so the UI can show it.
"""
from __future__ import annotations

from core.ai import cache, cost, routing
from core.ai.budget import TokenBudget
from core.ai.errors import NoKeyError, ProviderError
from core.ai.factory import get_provider
from core.ai.types import CompletionResult, EmbeddingResult, Message


class LLMManager:
    def __init__(self, budget: TokenBudget | None = None, run_id: int | None = None):
        self.budget = budget or TokenBudget(None)
        self.run_id = run_id

    # -- text completion --------------------------------------------------- #
    def run_task(self, task: str, messages: list[Message], *,
                 json_mode: bool = False) -> CompletionResult:
        route = routing.get_route(task)
        params = {"temperature": route.temperature, "max_tokens": route.max_tokens,
                  "json_mode": json_mode}

        cache_on = cache.enabled_for(task)
        cache_key = None
        if cache_on:
            prov, model = route.chain()[0]
            cache_key = cache.make_key(prov, model, messages, params)
            hit = cache.get(cache_key)
            if hit is not None:
                hit.task = task
                cost.record_usage(task=task, provider=hit.provider, model=hit.model,
                                  usage=hit.usage, cost_usd=0.0, from_cache=True,
                                  run_id=self.run_id)
                return hit

        result = self._walk_chain(task, route, messages, params, structured=None)
        if cache_on and cache_key is not None:
            cache.put(cache_key, result, cache.config().get("ttl_hours", 24))
        return result

    def run_structured(self, task: str, messages: list[Message], schema: dict
                       ) -> tuple[object, CompletionResult]:
        route = routing.get_route(task)
        params = {"temperature": route.temperature, "max_tokens": route.max_tokens,
                  "structured": True}
        result = self._walk_chain(task, route, messages, params, structured=schema)
        return result._structured_obj, result  # type: ignore[attr-defined]

    def _walk_chain(self, task, route, messages, params, structured):
        self.budget.allow()
        errors: list[str] = []
        for depth, (provider_slug, model) in enumerate(route.chain()):
            try:
                provider = get_provider(provider_slug)
                if structured is not None:
                    obj, result = provider.complete_structured(
                        messages, structured, model,
                        temperature=route.temperature, max_tokens=route.max_tokens,
                        task=task)
                    result._structured_obj = obj  # type: ignore[attr-defined]
                else:
                    result = provider.complete(
                        messages, model, temperature=route.temperature,
                        max_tokens=route.max_tokens,
                        json_mode=params.get("json_mode", False), task=task)
                result.fallback_depth = depth
                self.budget.add(result.usage)
                cost.record_usage(
                    task=task, provider=provider_slug, model=model, usage=result.usage,
                    cost_usd=cost.estimate_cost(provider_slug, model, result.usage),
                    ok=True, fallback_depth=depth, run_id=self.run_id)
                return result
            except ProviderError as exc:
                errors.append(f"{provider_slug}:{model} -> {type(exc).__name__}")
                cost.record_usage(
                    task=task, provider=provider_slug, model=model, usage=_zero(),
                    cost_usd=0.0, ok=False, error_class=type(exc).__name__,
                    fallback_depth=depth, run_id=self.run_id)
                continue
        raise ProviderError(
            f"all providers failed for task '{task}': {'; '.join(errors)}")

    # -- embeddings -------------------------------------------------------- #
    def embed_task(self, task: str, texts: list[str]) -> EmbeddingResult:
        route = routing.get_route(task)
        errors: list[str] = []
        for depth, (provider_slug, model) in enumerate(route.chain()):
            try:
                provider = get_provider(provider_slug)
                result = provider.embed(texts, model)
                cost.record_usage(
                    task=task, provider=provider_slug, model=model, usage=result.usage,
                    cost_usd=cost.estimate_cost(provider_slug, model, result.usage),
                    ok=True, fallback_depth=depth, run_id=self.run_id)
                return result
            except ProviderError as exc:
                errors.append(f"{provider_slug}:{model} -> {type(exc).__name__}")
                continue
        raise ProviderError(f"all providers failed for embeddings: {'; '.join(errors)}")


def _zero():
    from core.ai.types import Usage
    return Usage()


# --------------------------------------------------------------------------- #
# Convenience: capability probe used by settings / the app to decide whether any
# LLM path is available at all.
# --------------------------------------------------------------------------- #
def any_provider_ready() -> bool:
    from core.ai.keystore import default_store
    store = default_store()
    from core.ai.registry import PROVIDERS
    for slug, spec in PROVIDERS.items():
        if not spec.needs_key or store.has_key(slug):
            return True
    return False
