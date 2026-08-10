"""Drift AI provider layer (Phase 3).

Public surface:
  LLMManager            — orchestrates routing/fallback/cache/cost/budget
  build_provider/get_provider — construct a single provider
  KeyStore/default_store — secure key storage
  TokenBudget           — per-run token budget
  Message, CompletionResult, ... — value types
  PROVIDERS, routing, cost, cache — config/introspection
"""
from core.ai.budget import TokenBudget
from core.ai.factory import build_provider, get_provider, reset_providers
from core.ai.keystore import KeyStore, default_store, masked, reset_default_store
from core.ai.manager import LLMManager, any_provider_ready
from core.ai.registry import PROVIDERS, get_spec
from core.ai.types import (
    CompletionResult,
    ConnectionStatus,
    EmbeddingResult,
    Message,
    ModelInfo,
    Usage,
)

__all__ = [
    "LLMManager", "any_provider_ready", "build_provider", "get_provider",
    "reset_providers", "KeyStore", "default_store", "masked",
    "reset_default_store", "TokenBudget", "PROVIDERS", "get_spec",
    "Message", "CompletionResult", "EmbeddingResult", "ConnectionStatus",
    "ModelInfo", "Usage",
]
