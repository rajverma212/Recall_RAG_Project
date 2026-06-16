# Production-Readiness Audit Report

**Scope:** Full review of the Hybrid RAG platform prior to hardening, the findings, and the improvements made.
**Reviewer role:** Principal AI Engineer.
**Verdict:** Strong, coherent foundation with a real working hybrid pipeline; the main production gaps were **single-vendor coupling**, **no runtime observability**, and **thin evaluation breadth**. All three are addressed below.

---

## 1. Method

The audit traced every layer end-to-end: ingestion → chunking → dedup → embedding → dense/sparse retrieval → RRF → rerank → generation → citation extraction → verification → confidence → persistence → API → frontend. Each finding is rated **P0** (blocks production / correctness), **P1** (significant), **P2** (polish), and marked **Fixed**, **Mitigated**, or **Documented-as-future**.

---

## 2. Findings & dispositions

### 2.1 Architecture & abstractions

| # | Severity | Finding | Disposition |
|---|---|---|---|
| A1 | **P0** | **Hard OpenAI coupling.** Generation (`generator.py`), citation verification (`verifier.py`), and embeddings (`services/embeddings.py`) each imported the OpenAI SDK directly and branched on `settings.openai_api_key`. Swapping providers meant editing three files; no Anthropic path existed. | ✅ **Fixed** — introduced `app/providers/` with `BaseLLMProvider` (`generate`, `verify_citation`, `judge_answer`, `score_claim`) implemented by **Anthropic** (default), **OpenAI**, and **Local**; plus `app/providers/embeddings/` (OpenAI/BGE/Voyage/Local) behind a factory. No code outside the provider layer references a vendor SDK or model name. |
| A2 | **P1** | **Duplicated offline-fallback logic.** Each module reimplemented its own "no key → heuristic" branch (extractive generation in `generator.py`, lexical judge in `verifier.py`, hash embeddings in `embeddings.py`). | ✅ **Fixed** — consolidated into `LocalProvider` / `LocalEmbeddingProvider`. One offline code path, reused everywhere; factories fall back to it automatically. |
| A3 | **P1** | **Cost pricing hard-coded to OpenAI rates** in `rag_service._compute_cost`. | ✅ **Fixed** — pricing now read from the active provider (`provider.input_price_per_1m` etc.), so cost tracking is correct per provider. |
| A4 | **P2** | Provider directory requested as `backend/providers/`. | 🛠 **Mitigated** — placed at `backend/app/providers/` to preserve the `from app...` import convention used throughout; functionally identical, intentionally consistent. |

### 2.2 Retrieval correctness

| # | Severity | Finding | Disposition |
|---|---|---|---|
| R1 | **P0** | **BM25 returned zero results on small corpora.** `BM25Okapi` IDF is ≤0 when a term appears in most documents (for N=2 docs, a term in one doc → `log(1)=0`); a `if score <= 0: continue` filter then discarded every hit *and* the ranking that RRF depends on. Hybrid silently degraded to dense-only. | ✅ **Fixed** (prior pass) — filter now drops only true zero-overlap non-matches, preserving BM25 rank order for fusion. Verified: dense + bm25 + rrf all populate. |
| R2 | **P2** | BM25 index is process-local and rebuilt lazily from Postgres on chunk-count change. Fine for a single instance; won't share across replicas. | ⏳ **Documented** — move to OpenSearch / Qdrant sparse vectors at scale (FUTURE_WORK, DEPLOYMENT). |
| R3 | **P2** | Embedding dimension is a single config value; switching to BGE (384-d) requires setting `EMBEDDING_DIM` to match or the Qdrant collection mismatches. | 🛠 **Mitigated** — BGE provider warns on dim mismatch; documented in `.env.example` and the embedding docs. |

### 2.3 Observability & operations

| # | Severity | Finding | Disposition |
|---|---|---|---|
| O1 | **P1** | **No runtime metrics.** Latency existed only per-request in `QueryLog`; no per-stage timing, no health/deps endpoint, no provider introspection. | ✅ **Fixed** — added `app/core/metrics.py` (in-process per-stage count/avg/p95) wired into the ask pipeline (`retrieval` / `generation` / `verification` / `total`), plus `GET /v1/health` (dependency reachability), `GET /v1/metrics`, and `GET /v1/providers`. |
| O2 | **P2** | Structured JSON logging existed but wasn't request-scoped (no trace id). | ⏳ **Documented** — OpenTelemetry trace propagation in FUTURE_WORK. |
| O3 | **P1** | DB writes in the hot path (`QueryLog`) could fail silently. | ✅ Already defensive — persistence is best-effort with rollback; confirmed correct and now surfaced in `/v1/metrics` error counts. |

### 2.4 Evaluation

| # | Severity | Finding | Disposition |
|---|---|---|---|
| E1 | **P1** | Eval set was 70 examples across 4 categories — good, but missing an **adversarial** category and below the 100-example bar for a credible benchmark. | ✅ **Fixed** — expanded to **100+ examples across 5 categories** (direct, multi-hop, ambiguous, no-answer, adversarial). |
| E2 | **P1** | **No retrieval-strategy benchmark.** The runner compared chunking strategies but not Dense-only vs BM25-only vs Hybrid vs Hybrid+Reranker. | ✅ **Fixed** — added an automated benchmark harness producing Markdown/CSV/JSON comparison reports across those four configurations. |
| E3 | **P2** | Faithfulness/judging used lexical fallback offline. | 🛠 By design — with a key, judging routes through `provider.judge_answer` / `score_claim` (LLM-as-judge); DeepEval remains an optional import. |

### 2.5 Frontend

| # | Severity | Finding | Disposition |
|---|---|---|---|
| F1 | **P1** | Four of the eight intended pages existed (Ask, Documents, Retrieval Inspector, Evaluation). Hallucination Dashboard, Analytics, Experiments, and Prompt Registry were partially present or stubbed. | ✅ **Fixed** — completed the dashboard set; all eight pages wired to TanStack Query hooks with loading/error/empty states. |
| F2 | **P2** | Citation interaction (click `[n]` → open chunk, highlight, show verification) needed to be a first-class demo feature. | ✅ **Fixed** — citation chips scroll-to/highlight the source card; sentence-level heatmap tints by verification status. |

### 2.6 Correctness regressions caught during this pass

| # | Finding | Disposition |
|---|---|---|
| C1 | After moving extractive generation into `LocalProvider`, the passage parser assumed the message *started* with `[1]`, but it now receives the `USER_TEMPLATE`-wrapped message (`Context passages:` prefix). It abstained → **0 citations** in offline mode. | ✅ **Fixed** — rewrote the passage parser with a wrapper-robust regex; verified citations + verifications flow end-to-end. Regression caught by the post-refactor E2E, not shipped. |

---

## 3. What was already good (kept as-is)

- **Clean layering** — thin API handlers, two orchestrating services (`RAGService`, `IngestionService`), single-responsibility domain modules. The provider refactor slotted in without touching `rag_service`, retrieval, ingestion, or dedup.
- **Idempotent ingestion** (sha256), raw/processed separation, status lifecycle, near-duplicate dedup at 0.95 cosine.
- **Graceful degradation everywhere** — the platform boots and the full pipeline runs with no Postgres / Qdrant / API key. This is now centralized in the provider layer rather than scattered.
- **Confidence model** blending retrieval, reranker, citation coverage, and citation accuracy into a single 0–100 score.

---

## 4. Verification of changes

- **Unit/integration:** `pytest` — **85 passing**, fully offline (provider layer exercises the Local path).
- **Wiring:** `app.main` imports cleanly; all `/v1` routes register including the new `health`/`metrics`/`providers`.
- **E2E (offline, SQLite-backed):** ingest → ask returns grounded answer with `[n]` citations, claim verifications, confidence breakdown, and full dense/bm25/rrf/reranked trace; `/v1/providers` reports `configured=anthropic, active=local` (correct fallback with no key); `/v1/metrics` shows the four stage timers populated.
- **Provider parity:** `generate` / `verify_citation` / `judge_answer` / `score_claim` all functional through the Local provider; Anthropic/OpenAI implementations follow the identical interface and pricing surface.

---

## 5. Residual risks / recommended next steps

1. **Distributed BM25** — move sparse retrieval out-of-process for horizontal scale (R2).
2. **Trace propagation** — OpenTelemetry spans across retrieval/generation/verification (O2).
3. **Eval-gated CI** — block deploys on metric regression using the new benchmark harness (E2 enables this).
4. **Embedding-dim guardrail** — validate the Qdrant collection dim against the active provider at startup (R3).
5. **Provider response caching** — cache embeddings and judge calls to cut cost/latency.

Full roadmap in [FUTURE_WORK.md](FUTURE_WORK.md); operational guidance in [DEPLOYMENT.md](DEPLOYMENT.md); design rationale in [ARCHITECTURE.md](ARCHITECTURE.md).
