"""Phase 3 — AI provider layer tests.

No real network calls: the HTTP layer is stubbed. Focus is the security-critical
and correctness-critical behaviour — host assertion, key redaction, keystore
round-trip, retry classification, structured repair, routing fallback, cost math,
cache, and the token budget.
"""
from __future__ import annotations

from contextlib import closing

import pytest

import db
from core.ai import cache, cost, routing
from core.ai.budget import TokenBudget
from core.ai.errors import (
    AuthError,
    BadResponseError,
    BudgetExceededError,
    HostMismatchError,
    RateLimitError,
    ServerError,
    redact,
)
from core.ai.jsonutil import extract_json, validate
from core.ai.keystore import KeyStore, masked
from core.ai.registry import PROVIDERS, get_spec
from core.ai.types import Message, Usage


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    from db import connection
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    db.init_db()
    return p


# --------------------------------------------------------------------------- #
# Error redaction — a key must never survive into an error message
# --------------------------------------------------------------------------- #
class TestRedaction:
    def test_literal_key_scrubbed(self):
        assert "sk-secret123456789" not in redact("boom sk-secret123456789 bad", "sk-secret123456789")

    def test_key_shaped_tokens_scrubbed_without_literal(self):
        assert redact("auth failed for gsk_ABCDEFGHIJKLMNOP token") .count("gsk_") == 0
        assert "***" in redact("Bearer abcdefghij1234567890")

    def test_error_construction_redacts(self):
        e = AuthError("bad key gsk_ABCDEFGHIJKLMNOP", provider="groq",
                      secrets=("gsk_ABCDEFGHIJKLMNOP",))
        assert "gsk_ABCDEFGHIJKLMNOP" not in str(e)


# --------------------------------------------------------------------------- #
# Host assertion — a key only ever transits to its own provider's host
# --------------------------------------------------------------------------- #
class TestHostAssertion:
    def test_mismatched_host_is_hard_stop(self):
        from core.ai import http
        spec = get_spec("openai")
        with pytest.raises(HostMismatchError):
            http.request(spec, "GET", "https://evil.example.com/v1/models",
                         key="sk-abc123456789")

    def test_registered_host_passes_assertion(self, monkeypatch):
        from core.ai import http

        class FakeResp:
            status_code = 200
            def json(self): return {"data": []}
        monkeypatch.setattr(http.requests, "request", lambda *a, **k: FakeResp())
        spec = get_spec("openai")
        resp = http.request(spec, "GET", spec.models_url, key="sk-abc123456789")
        assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# Retry classification
# --------------------------------------------------------------------------- #
class TestRetry:
    def _fake_response(self, status, headers=None):
        class R:
            status_code = status
            def __init__(s): s.headers = headers or {}
            @property
            def text(s): return "body"
            def json(s): return {}
        return R()

    def test_401_raises_immediately_no_retry(self, monkeypatch):
        from core.ai import http
        calls = {"n": 0}
        def fake(*a, **k):
            calls["n"] += 1
            return self._fake_response(401)
        monkeypatch.setattr(http.requests, "request", fake)
        with pytest.raises(AuthError):
            http.request(get_spec("openai"), "GET", get_spec("openai").models_url,
                         key="k", sleep=lambda s: None)
        assert calls["n"] == 1  # never retried

    def test_429_retries_then_raises(self, monkeypatch):
        from core.ai import http
        calls = {"n": 0}
        def fake(*a, **k):
            calls["n"] += 1
            return self._fake_response(429, {"Retry-After": "0"})
        monkeypatch.setattr(http.requests, "request", fake)
        with pytest.raises(RateLimitError):
            http.request(get_spec("groq"), "GET", get_spec("groq").models_url,
                         key="k", sleep=lambda s: None, max_retries=2)
        assert calls["n"] == 3  # initial + 2 retries

    def test_500_retries(self, monkeypatch):
        from core.ai import http
        calls = {"n": 0}
        def fake(*a, **k):
            calls["n"] += 1
            return self._fake_response(500)
        monkeypatch.setattr(http.requests, "request", fake)
        with pytest.raises(ServerError):
            http.request(get_spec("groq"), "GET", get_spec("groq").models_url,
                         key="k", sleep=lambda s: None, max_retries=1)
        assert calls["n"] == 2


# --------------------------------------------------------------------------- #
# Keystore — AES fallback backend round-trip (never touches real Credential Mgr)
# --------------------------------------------------------------------------- #
class TestKeyStore:
    def test_round_trip_and_masking(self, tmp_path):
        ks = KeyStore(fallback_dir=tmp_path, force_file=True)
        assert ks.backend_name == "_AesFileBackend"
        ks.set_key("groq", "gsk_ABCDEFGHIJKLMNOPQRST")
        assert ks.get_key("groq") == "gsk_ABCDEFGHIJKLMNOPQRST"
        assert ks.has_key("groq")
        assert ks.masked_key("groq") == "gsk…QRST"
        assert "ABCDEFGHIJ" not in ks.masked_key("groq")

    def test_delete(self, tmp_path):
        ks = KeyStore(fallback_dir=tmp_path, force_file=True)
        ks.set_key("openai", "sk-abcdefghij12345")
        ks.delete_key("openai")
        assert not ks.has_key("openai")

    def test_encrypted_at_rest(self, tmp_path):
        ks = KeyStore(fallback_dir=tmp_path, force_file=True)
        ks.set_key("groq", "gsk_PLAINTEXTSHOULDNOTAPPEAR")
        blob = (tmp_path / "keys.enc").read_text("utf-8")
        assert "PLAINTEXTSHOULDNOTAPPEAR" not in blob  # AES-GCM, not plaintext

    def test_legacy_env_import(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_FROMENV1234567890")
        ks = KeyStore(fallback_dir=tmp_path, force_file=True)
        assert ks.get_key("groq") == "gsk_FROMENV1234567890"
        # Imported into the store so a second read doesn't depend on the env.
        monkeypatch.delenv("GROQ_API_KEY")
        assert ks.get_key("groq") == "gsk_FROMENV1234567890"

    def test_masked_helper(self):
        assert masked("short") == "****"
        assert masked("gsk_abcdefghijklmnop") == "gsk…mnop"


# --------------------------------------------------------------------------- #
# JSON utilities
# --------------------------------------------------------------------------- #
class TestJsonUtil:
    def test_extract_plain(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_extract_fenced(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_extract_with_prose(self):
        assert extract_json('Here you go: {"a": [1,2]} done') == {"a": [1, 2]}

    def test_validate_ok(self):
        schema = {"type": "object", "required": ["x"],
                  "properties": {"x": {"type": "integer"}}}
        assert validate({"x": 5}, schema) == []

    def test_validate_reports_errors(self):
        schema = {"type": "object", "required": ["x"],
                  "properties": {"x": {"type": "integer"}}}
        assert validate({}, schema)          # missing required
        assert validate({"x": "str"}, schema)  # wrong type


# --------------------------------------------------------------------------- #
# Structured output with repair (provider stubbed via _chat)
# --------------------------------------------------------------------------- #
class TestStructuredRepair:
    def _provider(self, replies):
        from core.ai.factory import build_provider
        from core.ai.types import CompletionResult
        p = build_provider("groq")
        seq = iter(replies)

        def fake_chat(messages, model, *, temperature, max_tokens, json_mode):
            return CompletionResult(text=next(seq), usage=Usage(10, 5),
                                    model=model, provider="groq")
        p._chat = fake_chat  # type: ignore
        return p

    def test_valid_first_try(self):
        p = self._provider(['{"skills": ["Python"]}'])
        schema = {"type": "object", "required": ["skills"],
                  "properties": {"skills": {"type": "array"}}}
        obj, res = p.complete_structured([Message("user", "x")], schema, "m")
        assert obj == {"skills": ["Python"]}

    def test_repairs_then_succeeds(self):
        p = self._provider(['not json at all', '{"skills": ["Python"]}'])
        schema = {"type": "object", "required": ["skills"],
                  "properties": {"skills": {"type": "array"}}}
        obj, res = p.complete_structured([Message("user", "x")], schema, "m")
        assert obj == {"skills": ["Python"]}
        assert res.usage.total_tokens == 30  # both calls billed

    def test_hard_fail_after_repair(self):
        p = self._provider(['garbage', 'still garbage'])
        schema = {"type": "object", "required": ["skills"],
                  "properties": {"skills": {"type": "array"}}}
        with pytest.raises(BadResponseError):
            p.complete_structured([Message("user", "x")], schema, "m")


# --------------------------------------------------------------------------- #
# Routing + fallback (manager walks the chain)
# --------------------------------------------------------------------------- #
class TestRoutingFallback:
    def test_default_route_is_groq(self, dbpath):
        r = routing.get_route("job_rerank")
        assert r.provider == "groq"
        assert r.chain()[0] == ("groq", "llama-3.3-70b-versatile")

    def test_override_persists(self, dbpath):
        routing.set_route("cover_letter", "anthropic", "claude-opus-5", temperature=0.5)
        r = routing.get_route("cover_letter")
        assert (r.provider, r.model, r.temperature) == ("anthropic", "claude-opus-5", 0.5)

    def test_manager_walks_to_fallback_on_failure(self, dbpath, monkeypatch):
        from core.ai import manager as mgr_mod
        from core.ai.types import CompletionResult

        # Route: primary fails (auth), fallback succeeds.
        routing.set_route("job_rerank", "groq", "primary-model",
                          fallback=[{"provider": "groq", "model": "backup-model"}])

        class FakeProvider:
            def complete(self, messages, model, **kw):
                if model == "primary-model":
                    raise AuthError("no key", provider="groq")
                return CompletionResult(text="ok", usage=Usage(3, 2),
                                        model=model, provider="groq")
        monkeypatch.setattr(mgr_mod, "get_provider", lambda slug: FakeProvider())

        m = mgr_mod.LLMManager()
        result = m.run_task("job_rerank", [Message("user", "hi")])
        assert result.model == "backup-model"
        assert result.fallback_depth == 1


# --------------------------------------------------------------------------- #
# Cost meter
# --------------------------------------------------------------------------- #
class TestCost:
    def test_estimate_uses_model_specific_rate(self, dbpath):
        # groq 8b: [0.05, 0.08] per 1M
        c = cost.estimate_cost("groq", "llama-3.1-8b-instant", Usage(1_000_000, 1_000_000))
        assert c == pytest.approx(0.05 + 0.08)

    def test_ollama_is_free(self, dbpath):
        assert cost.estimate_cost("ollama", "llama3.1", Usage(9_999, 9_999)) == 0.0

    def test_user_override_and_estimate_flag(self, dbpath):
        assert cost.pricing_is_estimate("groq") is True
        cost.set_price("groq", "default", 1.0, 2.0)
        assert cost.pricing_is_estimate("groq") is False

    def test_usage_ledger_aggregates(self, dbpath):
        cost.record_usage(task="job_rerank", provider="groq", model="m",
                          usage=Usage(1000, 500), cost_usd=0.01)
        cost.record_usage(task="cover_letter", provider="groq", model="m",
                          usage=Usage(2000, 1000), cost_usd=0.02)
        summ = cost.spend_summary("all")
        assert summ["cost_usd"] == pytest.approx(0.03)
        assert summ["by_task"]["job_rerank"] == pytest.approx(0.01)


# --------------------------------------------------------------------------- #
# Prompt cache
# --------------------------------------------------------------------------- #
class TestCache:
    def test_put_get_round_trip(self, dbpath):
        from core.ai.types import CompletionResult
        msgs = [Message("user", "score these")]
        key = cache.make_key("groq", "m", msgs, {"temperature": 0.2})
        assert cache.get(key) is None
        cache.put(key, CompletionResult(text="cached", usage=Usage(1, 1),
                                        model="m", provider="groq", task="job_rerank"), 24)
        hit = cache.get(key)
        assert hit is not None and hit.text == "cached" and hit.from_cache

    def test_purge(self, dbpath):
        from core.ai.types import CompletionResult
        key = cache.make_key("groq", "m", [Message("user", "x")], {})
        cache.put(key, CompletionResult(text="c", usage=Usage(), model="m",
                                        provider="groq"), 24)
        assert cache.purge() == 1
        assert cache.get(key) is None

    def test_rerank_cached_by_default(self, dbpath):
        assert cache.enabled_for("job_rerank") is True
        assert cache.enabled_for("resume_parse") is False


# --------------------------------------------------------------------------- #
# Token budget
# --------------------------------------------------------------------------- #
class TestBudget:
    def test_unlimited_never_blocks(self):
        b = TokenBudget(None)
        b.add(Usage(10 ** 9, 10 ** 9))
        b.allow()  # no raise

    def test_hard_stop(self):
        b = TokenBudget(100)
        b.add(Usage(60, 50))  # 110 > 100
        with pytest.raises(BudgetExceededError):
            b.allow()

    def test_warns_at_80_percent(self):
        seen = {}
        b = TokenBudget(100, on_warn=lambda spent, limit: seen.update(spent=spent))
        b.add(Usage(50, 35))  # 85 >= 80
        assert seen.get("spent") == 85
