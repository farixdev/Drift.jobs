# Drift

A local-first job-discovery desktop app. Point it at your résumé, and it fans out
across compliant job sources, dedupes the same role across boards, and ranks what's
left against your résumé with an explainable score — then helps you tailor, apply,
and track.

Runs fully offline with local scoring; add a provider key for AI extraction,
tailoring, and cover letters. **Bring your own key** — nothing is sent anywhere
you don't configure.

## Highlights
- **Compliant sources.** Employer-canonical ATS boards (Greenhouse, Lever, Ashby,
  Workable) + curated key-free feeds. Every source is robots-respecting with an
  honest user-agent; detection-evasion sources were removed (see
  `docs/SOURCES_REJECTED.md`).
- **Concurrent engine.** Bounded worker pool, per-domain rate limiting, priority
  ordering, retries with jittered backoff, circuit breakers, checkpointing, live
  cancellation, and a streaming run view.
- **Real deduplication.** The same role across many boards collapses to one
  record (content fingerprint + simhash), keeping the most authoritative source
  and a "seen on N sites" badge.
- **Explainable ranking.** Lexical BM25 → semantic embeddings → LLM rerank,
  blended with a freshness decay. Every job shows its sub-scores and rationale.
- **Résumé intelligence.** Structured parsing into an editable form, a transparent
  8-dimension match rubric, and honest tailoring — bullets are rephrased, never
  fabricated (a safety net reverts invented metrics/skills; you approve every diff).
- **Bring-your-own-key AI.** Eight providers (Anthropic, OpenAI, Gemini, Groq,
  OpenRouter, Mistral, DeepSeek, Ollama) behind one router with per-task model
  routing, fallback chains, a prompt cache, and a cost meter. Keys live in the OS
  keychain.
- **Track applications.** A Kanban pipeline with funnel metrics and export.

## Quick start

**Windows — one click:** double-click **`run.bat`**. On first run it creates the
virtual environment, installs dependencies, and launches the app; after that it
just launches.

**Manual (any OS):**
```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
.venv\Scripts\python main.py
```

Then:
1. Upload a résumé (Search screen).
2. Pick sources and a match threshold, or open the **Advanced search builder** for
   full criteria (role, location, salary, seniority, freshness, volume, …).
3. Run the scan — watch sources stream in — then review, tailor, and track.

No key needed to start. Add one in **Settings** for AI features.

## Design system
Press **Ctrl+Shift+D** in-app for the live component gallery (macOS/iOS system
aesthetic, light + dark). **Ctrl+K** opens the command palette.

## Documentation
- `docs/AUDIT.md` — the original repo audit that grounded the rebuild.
- `docs/ARCHITECTURE.md` — how it's built, phase by phase.
- `docs/DESIGN_SYSTEM.md` — tokens, components, motion.
- `docs/AI_PROVIDERS.md` — providers, key safety, routing.
- `docs/SOURCES.md` / `docs/SOURCES_REJECTED.md` / `docs/COMPLIANCE.md` — source
  posture and what Drift will not do.
- `docs/RUNBOOK.md` — run, test, troubleshoot.

## Compliance
Drift respects `robots.txt`, uses an honest user-agent, and never solves CAPTCHAs,
evades bot detection, bypasses paywalls/logins, or accesses accounts you don't
hold. See `docs/COMPLIANCE.md`.
