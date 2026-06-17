# Final Productionization Audit — Hybrid RAG Platform (Recall)

**Date:** 2026-06-16
**Branch:** `production-hardening`
**Auditor pass:** Principal-engineer end-to-end review prior to the final productionization pass.
**Scope:** Audit only — no code changed while producing this document. Findings drive Phases 2–9.

---

## 0. Executive summary

The platform is **architecturally sound and feature-complete** for a portfolio-grade hybrid RAG system. The provider-abstraction work from the previous session is well-executed: no code outside `app/providers/` touches a vendor SDK, and the whole pipeline runs offline via deterministic local providers (85 tests green with zero keys).

The remaining work is **productionization**, not construction. Five issues block a clean cloud deployment with Anthropic as the live provider; the rest are hardening, observability completeness, documentation, and CI. None require rebuilding anything.

**Deployment-ready today?** Locally via Docker Compose on the offline/local providers: **yes**. With Anthropic live in the cloud: **no** — see blockers B1–B3.

---

## 1. Architecture review

### 1.1 Shape

```
React/TS SPA (Vite, Tailwind, TanStack Query)
        │  /v1/*
FastAPI app
 ├── api/v1/        ask, documents, evaluations, analytics, experiments, system
 ├── services/      rag_service (orchestrator), ingestion_service, embeddings, vector_store
 ├── retrieval/     dense + bm25 → fusion (RRF) → reranker  (HybridRetriever)
 ├── generation/    generator (thin) + prompts
 ├── verification/  citations, verifier (thin), confidence
 ├── providers/     LLM: anthropic | openai | local      ← all vendor SDK code lives here
 │   └── embeddings/ openai | bge | voyage | local
 ├── evaluation/    runner, metrics, report
 ├── core/          config, logging, metrics (in-process registry)
 └── db/ models/    Postgres via SQLAlchemy 2.x
External: Postgres (metadata/analytics), Qdrant (vectors)
```

### 1.2 What is genuinely well done

- **Provider abstraction.** `BaseLLMProvider` / `BaseEmbeddingProvider` contracts are clean. Factories (`providers/factory.py`, `providers/embeddings/factory.py`) resolve config → concrete provider with an automatic `Local*` fallback on missing key / SDK / init error. Swapping vendors is a one-line env change. This is the strongest part of the codebase.
- **Offline-first.** `LocalProvider` + `LocalEmbeddingProvider` + in-memory `VectorStore` fallback keep the entire pipeline exercisable with no network/keys. This is what makes the test suite hermetic and CI cheap.
- **Layering discipline.** `generator.py`, `verifier.py`, `embeddings.py` are thin façades over the provider layer; the orchestrator (`rag_service.ask`) reads like the documented 10-step flow.
- **Cost/latency tracking.** `_compute_cost()` reads pricing from the *active* provider (not hard-coded), and `timed()` context managers feed the in-process metrics registry.
- **Determinism for tests.** Local heuristics (extractive generation, Jaccard entailment) exist to keep downstream stages testable, and are documented as such.

### 1.3 Data flow (ask)

`resolve prompt → retrieve (dense+bm25→RRF→rerank) → format context → generate → extract citations → verify each claim vs cited chunk → confidence (0–100) → cost+latency → persist QueryLog → AskResponse`. Streaming path mirrors this with token deltas. Both verified present and consistent.

---

## 2. Technical debt

| # | Item | Severity | Notes |
|---|------|----------|-------|
| D1 | `datetime.utcnow()` used throughout (`ingestion_service.py`, `evaluation/runner.py`, models) | Low | Deprecated in 3.12+; emits warnings (52 in test run). Should move to `datetime.now(UTC)`. Not a correctness bug. |
| D2 | `QueryLog` rollups in `/metrics` recomputed on every request via SQL aggregates | Low | Fine at portfolio scale; would need caching/materialization at volume. |
| D3 | In-process `MetricsRegistry` is per-instance | Medium | Correct and documented, but resets on restart and does not aggregate across replicas. Acceptable; flagged in FUTURE_WORK for OpenTelemetry. |
| D4 | BM25 index is in-process | Medium | Won't scale horizontally; already tracked in FUTURE_WORK. Out of scope for this pass. |
| D5 | `generation_temperature` setting exists but Anthropic provider intentionally ignores it | Low | Documented in `anthropic_provider.py`; harmless but slightly confusing. |
| D6 | Mixed persistence-fallback patterns (DB → JSON) in evaluation runner | Low | Pragmatic; keeps eval runnable without Postgres. |

---

## 3. Incomplete / partially-wired features

| # | Feature | State |
|---|---------|-------|
| I1 | Startup validation of provider + embedding-dim | **Missing.** Misconfiguration is discovered lazily at first request and only as a log line. Phase 2/3. |
| I2 | `/v1/providers` "provider status" | **Partial.** Reports active/available/keys-present, but not whether the active provider is actually *healthy* (reachable / usable). Phase 2. |
| I3 | `/v1/health` dependency set | **Partial.** Checks Postgres + Qdrant only; spec wants DB + vector store + active provider + retrieval system. Phase 7. |
| I4 | `/v1/metrics` business metrics | **Partial.** Exposes per-stage latency + some query rollups; missing explicit success rate and citation accuracy as first-class fields. Phase 7. |
| I5 | Embedding-dimension guardrail | **Missing.** See B2. Phase 3. |
| I6 | CI pipeline | **Missing.** No `.github/workflows`. Phase 5. |
| I7 | Cloud deployment configs (Vercel/Railway/Qdrant Cloud) | **Missing.** Only Docker Compose exists. Phase 6. |

---

## 4. Production risks

| # | Risk | Impact | Trigger |
|---|------|--------|---------|
| R1 | **Silent provider downgrade.** `LLM_PROVIDER=anthropic` with no/invalid key silently falls back to `LocalProvider`. | High | Production answers degrade to extractive heuristics with no alarm. Mitigation: startup validation that *fails fast* in `environment=production`, while preserving silent fallback in `local`/`ci`. Phase 2. |
| R2 | **Embedding dim mismatch.** Switching `EMBEDDING_PROVIDER` (e.g. openai 1536 → bge 384) against an existing Qdrant collection. | High | Qdrant rejects/garbles search at query time with an opaque error, or silently returns nonsense. Mitigation: startup dim check vs collection. Phase 3. |
| R3 | **Anthropic thinking param shape.** `thinking={"type": "adaptive"}` is not a valid Messages API value (API expects `{"type":"enabled","budget_tokens":N}`). | Medium | Any call with `ANTHROPIC_USE_THINKING=true` (verify/judge/score) raises a 400. Off by default, so latent. Phase 2 fix. |
| R4 | **CORS `allow_origins=["*"]` with `allow_credentials=True`.** | Low/Medium | Permissive for a public API; fine for a demo, should be tightened per-environment for production. Note in deployment guide. |
| R5 | **No request auth / rate limiting.** | Medium | Acceptable for a portfolio demo; must be called out as a known limitation before any real exposure. |

---

## 5. Deployment blockers

| # | Blocker | Detail | Fix phase |
|---|---------|--------|-----------|
| **B1** | **Anthropic key not forwarded in Docker.** `docker-compose.yml` `backend.environment` passes `OPENAI_API_KEY` but **not** `ANTHROPIC_API_KEY`, `LLM_PROVIDER`, `ANTHROPIC_MODEL`, `EMBEDDING_PROVIDER`. The default provider is `anthropic`, so in Docker it can *never* activate — it always falls back to local. | Phase 2/6 |
| **B2** | **No embedding-dim guardrail.** As R2; a wrong `EMBEDDING_DIM` vs collection is undetectable until query time. | Phase 3 |
| **B3** | **No cloud deploy path.** No Vercel (frontend), Railway (backend), or Qdrant Cloud configuration/guide. | Phase 6 |
| B4 | **No `.env` present.** Only `.env.example`. Expected (gitignored), but the deploy guide must spell out the exact variable set per platform, including the B1 variables. | Phase 6 |
| B5 | **README claims drift.** Advertises OpenAI-only fallback, "6 pages", omits Anthropic default + provider abstraction + the 3 new dashboards. Misrepresents the system to a reviewer. | Phase 4 |

---

## 6. Test coverage gaps

Current: 85 tests, fully offline, covering chunking, retrieval, generation/verification/confidence, ingestion. **Not covered:**

- Provider selection / fallback logic (`get_llm_provider`, `get_embedding_provider`).
- Embedding-dimension validation (new in Phase 3).
- System endpoints `/v1/health`, `/v1/metrics`, `/v1/providers` (no `TestClient` tests exist at all).

Phase 8 adds these.

---

## 7. Recommendations (→ phase mapping)

1. **Forward Anthropic config in Docker + add fail-fast startup validation** (B1, R1, I1) → **Phase 2**.
2. **Fix the Anthropic thinking param** to the documented `enabled/budget_tokens` shape (R3) → **Phase 2**.
3. **Add embedding-dimension guardrail** at startup with an actionable error, plus a Qdrant existing-collection check (B2, R2, I5) → **Phase 3**.
4. **Refresh README** to current reality (B5) → **Phase 4**.
5. **Eval-gated CI** with configurable faithfulness / citation-accuracy thresholds (I6) → **Phase 5**.
6. **Cloud deployment configs + guide** for Vercel / Railway / Qdrant Cloud (B3, B4, R4, R5) → **Phase 6**.
7. **Complete health/metrics/providers** to the spec'd surface (I2, I3, I4) → **Phase 7**.
8. **Add tests** for provider selection, embedding validation, and the system endpoints (§6) → **Phase 8**.

**Guiding constraint:** preserve all working functionality and the offline-first guarantee. Every change is additive or a localized hardening; nothing is rebuilt.

---

*End of audit. Subsequent phases implement §7 and are recorded in `docs/FINAL_PRODUCTION_REPORT.md`.*
