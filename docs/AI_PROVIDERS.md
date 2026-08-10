# AI Providers (Phase 3)

Drift is **bring-your-own-key**. It ships no keys, calls providers over raw HTTP
(no vendor SDKs), and routes every LLM task through a single manager with
fallback chains, structured-output repair, caching, and cost metering.

---

## Verification — 2026-08-10

Every provider's model-listing endpoint was probed live. For a bring-your-own-key
API, a `401`/`403` is a **pass**: it proves the endpoint exists and is correctly
auth-gated. A `404`/DNS failure would be a fail (wrong URL). Groq was probed with
a real key (full success); OpenRouter's model list is public.

| Provider | Base URL | `/models` probe | Auth | Embeddings | Verified |
|---|---|---|---|---|---|
| Anthropic | `https://api.anthropic.com/v1` | 401 — exists, gated ✅ | `x-api-key` | no | 2026-08-10 |
| OpenAI | `https://api.openai.com/v1` | 401 — exists, gated ✅ | Bearer | yes | 2026-08-10 |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | 403 — exists, gated ✅ | `x-goog-api-key` | yes | 2026-08-10 |
| Groq | `https://api.groq.com/openai/v1` | 200 — 15 models (live key) ✅ | Bearer | no | 2026-08-10 |
| OpenRouter | `https://openrouter.ai/api/v1` | 200 — 399 models (public) ✅ | Bearer | no | 2026-08-10 |
| Mistral | `https://api.mistral.ai/v1` | 401 — exists, gated ✅ | Bearer | yes | 2026-08-10 |
| DeepSeek | `https://api.deepseek.com/v1` | 401 — exists, gated ✅ | Bearer | no | 2026-08-10 |
| Ollama (local) | `http://localhost:11434/v1` | connection refused — offline path ✅ | none | yes | 2026-08-10 |

**Honest scope of "verified":** for the key-gated providers this confirms the URL,
path, and auth gating are correct — not that a completion succeeds with a key we
don't hold. Groq is fully exercised end-to-end (list models, structured
completion, cost metering) because this install has a Groq key. Ollama is the
offline path; "connection refused" is expected when it isn't running locally.

**Model names are never hardcoded as the source of truth.** At runtime each
provider's real model list is fetched from its `/models` endpoint with the user's
key and cached 24h. `core/ai/models_fallback.py` holds dated seed lists used only
when a live fetch fails; its `LAST_VERIFIED` is 2026-08-10. (Confirmed dynamic:
two probes on the same day returned different Groq catalogs — which is exactly why
the live fetch, not the constant, is authoritative.)

---

## Architecture

```
core/ai/
├── registry.py        ProviderSpec per provider: base_url, host, auth, embeddings
├── errors.py          typed errors; every message redacted of keys at construction
├── types.py           Message, Usage, CompletionResult, EmbeddingResult, ModelInfo
├── http.py            host assertion + retry (jittered backoff, Retry-After)
├── base.py            LLMProvider ABC + structured-output repair loop
├── openai_compat.py   OpenAI/Groq/OpenRouter/Mistral/DeepSeek/Ollama (one class)
├── native.py          Anthropic Messages + Gemini generateContent
├── factory.py         build_provider / get_provider
├── keystore.py        OS keychain (Windows Credential Manager) + AES-256-GCM fallback
├── models_fallback.py dated fallback model lists
├── routing.py         8 tasks -> (provider, model, params, fallback chain)
├── cost.py            editable price table + usage ledger + spend_summary
├── cache.py           prompt-response cache (hash of prompt+model+params, TTL)
├── budget.py          per-run token budget: hard stop + 80% warning
└── manager.py         LLMManager: routing + fallback + cache + cost + budget
```

Every provider implements the same interface: `complete`, `complete_structured`,
`stream`, `embed`, `list_models`, `test_connection`, `estimate_cost`. The six
OpenAI-compatible providers share one class parameterised by the registry spec;
Anthropic and Gemini are native adapters.

### Key safety (non-negotiable)

- **Storage:** OS keychain first (Windows Credential Manager via pywin32); where
  unavailable, AES-256-GCM at rest with a 0600 sidecar data key. Never plaintext.
- **Write-only from the UI:** keys are set and shown masked (`gsk…QRST`); the full
  value is never read back for display.
- **Never logged:** every error is redacted of the literal key and of key-shaped
  tokens at construction — so even a stored or re-raised error stays clean.
- **Host assertion:** before every request the target host is checked against the
  provider's registered host; a mismatch is a hard stop. A key only ever transits
  to its own provider, and never in a URL (Anthropic/Gemini use auth headers).
- **CI/commit guard:** `scripts/check_secrets.py` is a pre-commit hook that blocks
  committing key-shaped tokens. Install with `python scripts/check_secrets.py --install`.
- **Legacy `.env`:** an existing `GROQ_API_KEY` is imported into the keystore on
  first use; `.env` stays readable as a fallback so nothing breaks.

### Task routing

Eight tasks — `resume_parse`, `keyword_extract`, `query_expand`, `job_rerank`,
`job_explain`, `resume_tailor`, `cover_letter`, `embeddings` — each map to a
provider, model, temperature, max_tokens, and an ordered fallback chain. On a
retryable failure or a missing key the manager walks to the next entry, and the
served model is stamped onto the result (`result.label()`) so the UI can show
which model actually answered. Defaults target Groq (the provider this install
has a key for); embeddings default to local Ollama with an OpenAI fallback.
Overrides persist in the `ai.routing` setting.

### Reliability & cost

- Exponential backoff with **full jitter**, honouring `Retry-After`. Retries only
  429/5xx/timeout; 401/403 and other 4xx fail immediately.
- **Structured output:** JSON-schema-validated with exactly one repair retry that
  feeds the errors back, then a hard fail — malformed JSON is never silently
  accepted. Batched reranking scores N jobs per call.
- **Cost meter:** every call (including cache hits and failures) is logged to
  `llm_usage`; `cost.spend_summary()` aggregates by day/month/all, per provider
  and per task. Prices are **user-editable estimates** (`ai.pricing` setting) —
  the shipped `DEFAULT_PRICES` are seeds flagged as unverified, never presented as
  authoritative quotes.
- **Cache:** prompt-response cache keyed on `sha256(prompt+model+params)`, TTL
  configurable (`ai.cache`), on by default for `job_rerank`/`job_explain`. A hit
  is billed at zero and labelled `(cached)`. Purge via `cache.purge()`.
- **Budget:** a `TokenBudget` enforces a per-run hard stop and fires an 80% warning.

### Not yet built (deferred to the design phase)

The Settings UI for providers — connection-status dots, add-key sheet, per-task
model matrix, fallback-chain editor, cost dashboard, cache controls — is deferred
to **Phase 1 (design system)**, which the spec's execution order places after
this phase. The engine below it is complete and live-verified; the current
`SettingsDialog` continues to manage the Groq key via `.env` until the new UI
lands.
