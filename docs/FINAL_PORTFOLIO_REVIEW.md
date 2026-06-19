# Final Portfolio & Production Readiness Review — Recall (Hybrid RAG Platform)

**Date:** 2026-06-18
**Branch:** `production-hardening`
**Scope:** Final polish pass — fix remaining bugs, validate metrics, improve UX/presentation, re-verify deployment. No architecture changes; every fix is targeted and verified against the running stack.

---

## 1. Bugs found

| # | Severity | Bug | Root cause |
|---|----------|-----|------------|
| **B1** | **Critical** | **System page rendered a blank screen** — `TypeError: Cannot convert undefined or null to object` at `Object.entries(...)`. | The productionization pass changed `GET /v1/health` to return a richer `checks` object and dropped the old `dependencies` field, but `SystemStatusPage.tsx` still called `Object.entries(health.dependencies)`. `health.dependencies` was `undefined` → `Object.entries(undefined)` throws and unmounts the whole route. The `HealthResponse` TS type was also stale (`dependencies` instead of `checks`). |
| **B2** | **High** | **Analytics showed `AVG CONFIDENCE = 5842%`** (and the System summary card the same). | `QueryLog.confidence` is stored on a **0–100** scale (the confidence score is already a percentage). Both `AnalyticsPage` and `SystemStatusPage` multiplied it by 100 again (`avg_confidence * 100`), so 58.42 rendered as 5842%. |
| B3 | Low | Retrieval Inspector had no error state (failed query fell through to the empty state with no message). | `askMutation.error` was never rendered. |
| B4 | Low (latent) | `providers.llm.configured` was typed `boolean` but the backend returns the provider **name string** (`"anthropic"`). Rendered "Configured/Not configured" off a truthy string — misleading, not a crash. | Type drift after the providers endpoint gained a `status` block. |

**Validated as NOT bugs** (audited, calculations correct): Hallucination dashboard citation-accuracy / unsupported-rate / hallucination-risk (all derived from claim counts, correctly scaled); Evaluation page metrics (0–1 → ×100); Experiments page (`Object.entries(exp.metrics)` is guarded by `{exp.metrics && …}`); Analytics citation-accuracy and low-confidence-rate (0–1 → ×100, correct).

---

## 2. Bugs fixed

| # | Fix | Files |
|---|-----|-------|
| B1 | Rewrote `HealthResponse` type to the real `checks` shape; System page now reads `health.checks` null-safely and derives per-service health states. No code path touches `health.dependencies` anymore (verified in the shipped bundle). | `frontend/src/lib/types.ts`, `frontend/src/pages/SystemStatusPage.tsx` |
| B2 | Removed the extra `* 100` on `avg_confidence` in both places (value is already 0–100). | `frontend/src/pages/AnalyticsPage.tsx`, `frontend/src/pages/SystemStatusPage.tsx` |
| B3 | Added an error banner to Retrieval Inspector. | `frontend/src/pages/RetrievalInspectorPage.tsx` |
| B4 | Corrected provider types (`configured: string`, added `status` blocks); System page now shows configured **and** active provider with a Healthy/Degraded pill driven by `status.healthy`. | `frontend/src/lib/types.ts`, `frontend/src/pages/SystemStatusPage.tsx` |

---

## 3. Metrics audited & fixed

Audited every metric end-to-end (backend scale → frontend formatting → live value):

| Metric | Stored scale | Correct display | Status |
|---|---|---|---|
| Confidence | 0–100 | `xx.x%` (no ×100) | **Fixed** (was 5842%) — live value now 61.8% |
| Citation accuracy | 0–1 | `×100 → xx.x%` | Correct |
| Hallucination / unsupported rate | 0–1 (from counts) | `×100 → xx.x%` | Correct |
| Low-confidence rate | 0–1 | `×100 → xx.x%` | Correct |
| Latency | ms | `xxxx ms` | Correct |
| Cost | USD | `$x.xxxx` | Correct |
| Query counts | int | `toLocaleString()` | Correct |
| Eval metrics (recall/correctness/faithfulness) | 0–1 | `×100 → xx.x%` | Correct |

**Live evidence after fix** (`GET /v1/analytics`, 8 queries): `avg_confidence: 61.82` → renders **61.8%**; `avg_citation_accuracy: 0.49` → **49.0%**; `low_confidence_rate: 0.0` → **0.0%**. All bounded 0–100. Asserted programmatically during validation.

---

## 4. UI / UX improvements

- **System Status → operational dashboard.** New **Services** grid with **Healthy / Degraded / Offline** pills for Backend (+version), PostgreSQL, Qdrant (+ live vector count), LLM (provider/model/health), Embeddings (provider/dimension), and Retrieval. Plus configured-vs-active provider detail and the existing pipeline-latency chart. Backend now also surfaces `version` and the Qdrant `vectors` count on `/v1/health` (new `VectorStore.count()`).
- **Ask page — demo mode.** Added a **Sample questions** chip row that populates the query box (the five requested prompts) — ideal for walkthroughs and screenshots.
- **Documents.** Ingestion timestamp now shows date **and** time (with a full-timestamp tooltip).
- **Retrieval Inspector.** Added the missing error state.
- **Route audit (all 9 pages).** Verified each renders with loading + empty states and no console-throwing paths; added the one missing error banner. No blank screens remain.

---

## 5. Remaining limitations

- **Screenshots are not yet captured.** README embeds five images from `docs/screenshots/`; a [capture guide](screenshots/README.md) is included. They render once PNGs are saved. (Cannot be auto-captured headlessly here.)
- **Document file-size is not displayed** — the `Document` model doesn't persist byte size. Chunk count, pages, strategy, and timestamp are shown. Adding size needs a schema field + ingestion change (deferred; out of scope for a no-migration polish pass).
- **In-process BM25 index + metrics registry** remain single-instance (documented in `FUTURE_WORK.md` / `DEPLOYMENT_GUIDE.md`).
- **No auth / rate limiting / CORS lockdown** yet — required before untrusted public exposure.
- **Generation-quality eval metrics** are still offline-baselined; a keyed Anthropic eval run is needed to publish real numbers.
- **Latency is real-LLM bound** (~20–28 s per answer with Anthropic generation + per-claim verification calls). Acceptable for a demo; a verification-batching / async pass would reduce it.

---

## 6. Deployment readiness

Re-verified end-to-end on the running stack:

```
docker compose up -d --build      → UP_EXIT=0
docker compose ps:
  backend    Up        frontend   Up
  postgres   healthy   qdrant     healthy
GET /v1/health     → 200, status "ok", version 1.0.0,
                     checks {database:ok, vector_store:qdrant(vectors:4), llm:anthropic(active), retrieval:ok}
GET /v1/documents  → 200
Frontend (5173)    → 200, shipped bundle contains the new code, no `health.dependencies` access
Backend tests      → 104 passed · ruff clean · frontend tsc clean
```

**Verdict:** deployment path works; local and portfolio-cloud (Vercel/Railway/Qdrant Cloud, per `DEPLOYMENT_GUIDE.md`) are ready.

## 7. Resume readiness

- **Demonstrates production AI engineering**, not a notebook: provider abstraction, fail-fast config validation, operational health dashboard with live service states, eval-gated CI, Dockerized deploy.
- **The bugs that would embarrass in a demo are gone**: no blank System page, no 5842% metric. Every dashboard renders with correct, bounded numbers.
- **Demo-ready**: sample-question chips, a real end-to-end flow (ingest PDF → cited answer → trace → analytics) verified against live Claude.
- **Screenshots are one capture session away** (guide + embed slots in place).

## 8. Recommended next steps

1. **Capture the five screenshots** (guide in `docs/screenshots/README.md`) and commit them — the single highest-leverage portfolio step.
2. **Record a 60–90s demo video**: ingest a PDF → ask a sample question → show citations/heatmap → Retrieval Inspector → System dashboard.
3. **Run a keyed Anthropic evaluation** and publish real generation metrics; raise CI floors.
4. **Open a PR** `production-hardening` → `main` to land the whole productionization + polish pass.
5. Before any public exposure: **auth + rate limiting + CORS lockdown**.
6. Optional perf: **batch per-claim verification** to cut answer latency.

---

## Evidence appendix — live E2E (real PDF, real Claude)

```
INGEST  software_engineering.pdf → status=completed, num_chunks=1
DOCS    software_engineering.pdf (chunks=1, pages=1) + 2025 Resume.pdf
ASK     "What are the four process activities in software engineering?"
  ANSWER  lists Specification / Development / Validation / Evolution, grounded [1]
  CONF    85.58  (0–100, sane)
  CITES   [1] software_engineering.pdf p.1
  VERIFY  5 claims → 4 supported, 1 partially_supported
  TRACE   dense=4 · bm25=4 · rrf=4 · reranked=4   (all stages populated)
ANALYTICS avg_confidence 61.82 → 61.8% · citation_acc 0.49 → 49% · all bounded
HEALTH    vectors 3 → 4 after ingest (collection count live)
```
