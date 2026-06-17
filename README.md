<div align="center">

# 🔎 Recall — Hybrid RAG Platform

**A production-grade Retrieval-Augmented Generation system: hybrid retrieval, cross-encoder reranking, verifiable citations, hallucination detection, a pluggable multi-vendor model layer, an automated evaluation harness, and full runtime observability.**

`FastAPI` · `Pydantic v2` · `SQLAlchemy` · `PostgreSQL` · `Qdrant` · `Anthropic` · `OpenAI` · `React` · `TypeScript` · `Vite` · `TailwindCSS` · `TanStack Query` · `Docker`

</div>

---

## Why this is different from a typical RAG demo

Most RAG demos stop at *"embed → cosine search → stuff into a prompt."* Recall implements the parts that actually matter in production — and proves they work with an evaluation harness and observability, not just a happy-path screenshot.

| Capability | What it does |
|---|---|
| **Hybrid retrieval** | Dense (Qdrant vectors) **+** sparse (BM25) candidates fused with **Reciprocal Rank Fusion**, then reranked with a **cross-encoder** (`BAAI/bge-reranker-base`). |
| **Verifiable citations** | Every answer carries `[n]` markers mapped to exact source chunks, with the supporting quote span surfaced. |
| **Hallucination detection** | Each claim is verified against its cited chunk and labelled `supported` / `partially_supported` / `unsupported`; a citation heatmap tints the answer by trust. |
| **Pluggable model layer** | LLM and embeddings sit behind provider interfaces. Switch **Anthropic ↔ OpenAI ↔ local** (and embeddings across OpenAI/BGE/Voyage/local) with a one-line env change. No vendor SDK is imported outside `app/providers/`. |
| **Confidence scoring** | A single 0–100 score blends retrieval confidence, reranker confidence, citation coverage, and citation accuracy. |
| **Automated evaluation** | 70 labelled examples across *direct / multi-hop / ambiguous / no-answer* scored on retrieval recall, answer correctness, faithfulness, citation accuracy, and confidence calibration (ECE), with side-by-side config comparison reports. |
| **Observability** | `/v1/health`, `/v1/metrics`, `/v1/providers` plus per-query cost/latency tracking, prompt versioning, and analytics dashboards. |
| **Runs with zero external dependencies** | With no API keys the system uses deterministic local providers, an in-memory vector store, and an extractive generator — the **entire pipeline still runs** for demos, CI, and offline development. |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  React + TS SPA (Vite, Tailwind, TanStack Query)                   │
│  Ask · Documents · Retrieval Inspector · Hallucination · Analytics │
│  Evaluation · Experiments · Prompt Registry · System Status        │
└───────────────────────────────┬──────────────────────────────────┘
                                 │  /v1/*
┌───────────────────────────────▼──────────────────────────────────┐
│  FastAPI                                                           │
│  api/v1: ask · documents · evaluations · analytics · experiments  │
│          · system (health/metrics/providers)                      │
│                                                                    │
│  RAGService.ask()  ── orchestrator ──────────────────────────────┐ │
│   retrieve → format context → generate → cite → verify → score   │ │
│                                                                  │ │
│  Provider layer (only place vendor SDKs live):                   │ │
│   LLM:        anthropic | openai | local                         │ │
│   Embeddings: openai | bge | voyage | local                      │ │
│   → factories resolve config and fall back to local on no-key    │ │
└──────────┬──────────────────────────────────┬────────────────────┘ │
           │                                  │                       │
   ┌───────▼────────┐                ┌────────▼────────┐              │
   │   PostgreSQL   │                │     Qdrant      │ ◀────────────┘
   │ metadata,      │                │   dense vectors │
   │ chunks,        │                └─────────────────┘
   │ query logs,    │
   │ eval runs      │
   └────────────────┘
```

The retrieval pipeline:

```
Question
  → Dense retrieval   (embeddings → Qdrant, top-20)
  → Sparse retrieval  (BM25Okapi over chunk text, top-20)
  → Reciprocal Rank Fusion  (score = Σ wᵢ / (k + rankᵢ),  k = 60)
  → Cross-encoder rerank  (BAAI/bge-reranker-base)
  → Top-5 context
  → Grounded generation  (cite [n], never fabricate, state uncertainty)
  → Citation extraction + per-claim verification
  → Confidence score (0–100)
```

Full design rationale: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**, **[docs/FINAL_AUDIT.md](docs/FINAL_AUDIT.md)**.

---

## Features

- **Ask** — query the corpus; streamed answer with inline citations, confidence gauge, and per-claim verification.
- **Retrieval Inspector** — see every stage (dense, BM25, RRF, rerank) with per-candidate scores; understand *why* a chunk surfaced.
- **Hallucination Dashboard** — claim-level support breakdown and a heatmap that tints answers by trust.
- **Analytics Dashboard** — query volume, latency, confidence distribution, and cost rollups from the query log.
- **Evaluation** — run the labelled dataset, view aggregate + per-category metrics, and compare configurations side by side.
- **Experiments & Prompt Registry** — versioned prompts and A/B experiment tracking, DB-backed.
- **System Status** — live `/v1/health`, `/v1/metrics`, and `/v1/providers` (which provider/model is active, and whether a fallback is in effect).
- **Provider abstraction** — Anthropic (default, `claude-sonnet-4-6`), OpenAI, or a deterministic local provider; same for embeddings.
- **Fail-fast startup validation** — in production, a missing key (silent downgrade to local) or an embedding-dimension mismatch aborts boot with an actionable error; locally it degrades gracefully.

---

## Quick start (one command)

```bash
cp .env.example .env     # set ANTHROPIC_API_KEY for live Claude answers (optional)
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API + Swagger docs | http://localhost:8000/docs |
| Health / Providers | http://localhost:8000/v1/health · http://localhost:8000/v1/providers |
| Qdrant dashboard | http://localhost:6333/dashboard |

Open **Documents** → upload a PDF/Markdown/HTML/TXT → go to **Ask** and query it.

Load the bundled sample corpus + run an evaluation:

```bash
docker compose exec backend python scripts/seed_sample_data.py
docker compose exec backend python scripts/run_evaluation.py --name baseline --strategy recursive
docker compose exec backend python scripts/run_evaluation.py --compare   # fixed vs recursive vs dense vs sparse
```

> **No keys?** Leave `ANTHROPIC_API_KEY` blank and everything still runs on the deterministic local provider. `GET /v1/providers` will report `configured=anthropic, active=local` so the fallback is never silent.

---

## Screenshots

> _Placeholders — capture from a running instance (`docker compose up`) and drop into `docs/screenshots/`._

| View | Placeholder |
|---|---|
| Ask + citations + confidence | `![Ask](docs/screenshots/ask.png)` _(pending)_ |
| Retrieval Inspector (stage scores) | `![Retrieval Inspector](docs/screenshots/retrieval.png)` _(pending)_ |
| Hallucination Dashboard (heatmap) | `![Hallucination](docs/screenshots/hallucination.png)` _(pending)_ |
| Analytics Dashboard | `![Analytics](docs/screenshots/analytics.png)` _(pending)_ |
| System Status (providers/health) | `![System](docs/screenshots/system.png)` _(pending)_ |

---

## Evaluation

The harness scores the RAG pipeline against a labelled dataset and persists every run (DB, with JSON fallback). Metrics: **retrieval recall, answer correctness, faithfulness, citation accuracy, confidence calibration (ECE)**, plus pass-rate and per-category breakdowns.

```bash
python scripts/run_evaluation.py --name baseline --strategy recursive --verbose
```

**Measured (provider-independent):**

| Metric | Score | Notes |
|---|---|---|
| Retrieval Recall | **0.91** | 70-example set, recursive chunking, hybrid fusion — retrieval is independent of the LLM provider. |

**Generation-quality metrics (answer correctness, faithfulness, citation accuracy):** _pending a full Anthropic eval run._ The numbers currently in `evaluation/reports/` were produced by the **deterministic local provider** (an extractive heuristic, not a real model) and are intentionally **not** quoted here as headline results — they understate live quality. Run the harness with `ANTHROPIC_API_KEY` set to populate these. See **[docs/EVALUATION.md](docs/EVALUATION.md)**.

The harness is designed to run as an eval-gated CI check that fails on metric regression — see **Deployment / CI** below for the planned wiring.

---

## Deployment

- **Local / demo:** Docker Compose — service architecture, health checks, env vars, and offline mode are documented in **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.
- **Cloud (planned):** the stack is cloud-deployable — Frontend → **Vercel**, Backend → **Railway**, Vectors → **Qdrant Cloud**, Postgres → Railway/Neon. A per-platform walkthrough is tracked in [docs/FUTURE_WORK.md](docs/FUTURE_WORK.md).
- **CI (planned):** a GitHub Actions workflow to run lint + the 104-test suite + the evaluation harness with configurable metric thresholds. Not yet wired — tracked in [docs/FUTURE_WORK.md](docs/FUTURE_WORK.md).

### Local development (without Docker)

```bash
# Backend
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000

# Frontend
cd frontend
npm install && npm run dev             # http://localhost:5173
```

> Backend boots even with no Postgres / Qdrant / API key — it degrades to offline fallbacks. Run `pytest` in `backend/` for the suite (**104 tests, fully offline**).

---

## System Design Decisions

- **Provider abstraction over direct SDK calls** — every model interaction goes through `BaseLLMProvider` / `BaseEmbeddingProvider`. Swapping vendors is one env var; the offline local provider keeps tests hermetic and CI free. No vendor lock-in.
- **Anthropic (`claude-sonnet-4-6`) as the default LLM** — strong grounded-generation and instruction-following for citation-constrained answering; the judge/verify path can optionally use extended thinking.
- **Qdrant over pgvector** — purpose-built ANN, payload filtering, horizontal scaling; keeps the vector workload off the OLTP database.
- **RRF over weighted-score fusion** — rank-based fusion is score-scale agnostic, so dense cosine and BM25 magnitudes combine without brittle normalization. See [docs/RETRIEVAL_PIPELINE.md](docs/RETRIEVAL_PIPELINE.md).
- **Cross-encoder rerank after fusion** — a bi-encoder retrieves cheaply at scale; the expensive cross-encoder only scores ~20 fused candidates, buying precision where it counts. See [docs/RERANKING.md](docs/RERANKING.md).
- **Post-hoc citation verification** — grounding is necessary but not sufficient; verifying each claim against its cited chunk turns "looks cited" into "is supported."
- **Fail-fast startup validation** — production aborts on silent provider downgrade or embedding-dimension mismatch; local/CI stay frictionless. See [backend/app/core/startup.py](backend/app/core/startup.py).
- **Everything configurable + logged** — chunking strategy, fusion weights, top-k, and prompt version are env/DB-driven so the evaluation harness can A/B them.

---

## Documentation

| Doc | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, components, data model, rationale |
| [FINAL_AUDIT.md](docs/FINAL_AUDIT.md) | Production-readiness audit: risks, blockers, dispositions |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker Compose, service architecture, env vars, offline mode |
| [RETRIEVAL_PIPELINE.md](docs/RETRIEVAL_PIPELINE.md) · [RERANKING.md](docs/RERANKING.md) | Dense + sparse + RRF; cross-encoder reranking |
| [CITATION_VERIFICATION.md](docs/CITATION_VERIFICATION.md) | Claim extraction, support checking, hallucination surfacing |
| [EVALUATION.md](docs/EVALUATION.md) | Dataset, metrics, ECE, comparison reports |
| [CHUNKING_STRATEGIES.md](docs/CHUNKING_STRATEGIES.md) · [INGESTION_PIPELINE.md](docs/INGESTION_PIPELINE.md) | Chunking trade-offs; ingestion + idempotency |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Every endpoint with schemas + curl examples |
| [FUTURE_WORK.md](docs/FUTURE_WORK.md) | Roadmap |

---

## Future Work

- **Distributed BM25** — move the in-process sparse index to OpenSearch or Qdrant sparse vectors for horizontal scale.
- **OpenTelemetry** — replace the in-process metrics registry with trace propagation + Prometheus export.
- **Response/embedding cache** — Redis layer for repeated queries.
- **Auth + rate limiting** — API keys / JWT and per-tenant quotas before any public exposure.
- **Advanced retrieval** — HyDE, ColBERT late interaction, and agentic multi-step retrieval.
- **Full Anthropic eval baseline** — publish generation-quality metrics from a keyed run and gate CI on them.

---

## Resume Impact

What this project demonstrates to a hiring team:

- **Production AI engineering, not a notebook** — vendor-abstracted model layer, fail-fast configuration validation, health/metrics/providers observability, and Docker/cloud deployment paths.
- **Retrieval quality you can defend** — hybrid dense+sparse fusion, cross-encoder reranking, and an evaluation harness that quantifies recall/faithfulness/calibration rather than asserting them.
- **Trustworthy generation** — verifiable citations and per-claim hallucination detection, surfaced in the UI.
- **Engineering maturity** — 104 offline tests, a CI-ready evaluation harness, layered architecture with clear seams, and thorough design docs.
- **Full-stack ownership** — typed React SPA, FastAPI backend, Postgres + Qdrant, all wired and observable end-to-end.

---

## License

MIT — built as a portfolio demonstration of production AI-engineering practices.
