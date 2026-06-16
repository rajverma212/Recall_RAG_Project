<div align="center">

# 🔎 Hybrid RAG Platform

**A production-grade Retrieval-Augmented Generation system with hybrid retrieval, cross-encoder reranking, verifiable citations, hallucination detection, and an automated evaluation harness.**

`FastAPI` · `Pydantic v2` · `SQLAlchemy` · `PostgreSQL` · `Qdrant` · `React` · `TypeScript` · `Vite` · `TailwindCSS` · `TanStack Query` · `Docker Compose`

</div>

---

## Why this project is different from a typical RAG demo

Most RAG demos stop at *"embed → cosine search → stuff into a prompt."* This platform implements the parts that actually matter in production:

| Capability | What it does |
|---|---|
| **Hybrid retrieval** | Dense (Qdrant vectors) **+** sparse (BM25) candidates fused with **Reciprocal Rank Fusion**, then reranked with a **cross-encoder** (`BAAI/bge-reranker-base`). |
| **Verifiable citations** | Every answer carries `[n]` markers mapped to exact source chunks, with the supporting quote span surfaced. |
| **Hallucination detection** | Each claim is verified against its cited chunk and labelled `supported` / `partially_supported` / `unsupported`. A **citation heatmap** tints the answer by trust. |
| **Confidence scoring** | A single 0–100 score blends retrieval confidence, reranker confidence, citation coverage, and citation accuracy. |
| **Near-duplicate dedup** | Chunks within 0.95 cosine similarity are skipped and logged, keeping the index clean. |
| **Automated evaluation** | 70 labelled examples across *direct / multi-hop / ambiguous / no-answer* with retrieval recall, answer correctness, faithfulness, citation accuracy, and confidence calibration (ECE), plus side-by-side config comparison reports. |
| **Observability** | Per-query cost tracking, latency, prompt versioning, experiment tracking, and a query-analytics dashboard. |
| **Runs with zero external dependencies** | Leave `OPENAI_API_KEY` blank and the system uses deterministic fallback embeddings, an in-memory vector store, a lexical reranker, and an extractive generator — the **entire pipeline still runs** for demos, CI, and offline development. |

---

## Architecture at a glance

```
                          ┌───────────────────────────────────────────────┐
   React + TS SPA  ─────▶ │                FastAPI  (/v1)                  │
   (Vite, Tailwind,       │                                               │
    TanStack Query)       │   /ask  /ingest  /documents  /evaluations     │
                          │   /analytics  /experiments  /prompts          │
                          └───────┬───────────────────────────┬───────────┘
                                  │                           │
                 ┌────────────────▼─────────┐     ┌───────────▼───────────┐
                 │     Ingestion pipeline    │     │   RAG / Ask pipeline   │
                 │  loaders → chunkers →     │     │  dense + BM25 → RRF →   │
                 │  embed → dedup → persist  │     │  rerank → generate →   │
                 └───────┬───────────┬───────┘     │  cite → verify → score │
                         │           │             └───────┬───────────────┘
                  ┌──────▼─────┐ ┌───▼──────┐              │
                  │ PostgreSQL │ │  Qdrant  │ ◀────────────┘
                  │ (metadata, │ │ (vectors)│
                  │  chunks,   │ └──────────┘
                  │  analytics)│
                  └────────────┘
```

Full design rationale: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Quick start (one command)

```bash
cp .env.example .env          # optionally set OPENAI_API_KEY for full quality
docker compose up --build
```

| Service  | URL |
|----------|-----|
| Frontend | http://localhost:5173 |
| API + Swagger docs | http://localhost:8000/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |

Then: open the **Documents** page → upload a PDF/Markdown/HTML/TXT file → go to **Ask** and query it.

To load the bundled sample corpus + run an evaluation:

```bash
docker compose exec backend python scripts/seed_sample_data.py
docker compose exec backend python scripts/run_evaluation.py --name baseline --strategy recursive
docker compose exec backend python scripts/run_evaluation.py --compare   # fixed vs recursive vs semantic
```

---

## The pipeline

```
Question
  → Dense retrieval   (OpenAI text-embedding-3-small → Qdrant, top-20)
  → Sparse retrieval  (BM25Okapi over chunk text, top-20)
  → Reciprocal Rank Fusion  (score = Σ wᵢ / (k + rankᵢ),  k = 60)
  → Cross-encoder rerank  (BAAI/bge-reranker-base)
  → Top-5 context
  → Grounded generation  (cite [n], never fabricate, state uncertainty)
  → Citation extraction + per-claim verification
  → Confidence score (0–100)
```

---

## Repository layout

```
backend/      FastAPI app: api/ core/ db/ models/ schemas/
              ingestion/ chunking/ retrieval/ generation/
              verification/ evaluation/ services/  + tests/
frontend/     React + TS + Vite SPA (6 pages, TanStack Query)
evaluation/   datasets/ (70 examples) + reports/  + README
docs/         11 architecture & pipeline documents
scripts/      seed_sample_data.py, run_evaluation.py
docker/       backend + frontend Dockerfiles, nginx config
sample_data/  raw/ (corpus) + processed/
docker-compose.yml
```

---

## Documentation

| Doc | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, components, data model, decision rationale |
| [INGESTION_PIPELINE.md](docs/INGESTION_PIPELINE.md) | Loaders, metadata, raw/processed separation, idempotency |
| [CHUNKING_STRATEGIES.md](docs/CHUNKING_STRATEGIES.md) | Fixed vs recursive vs semantic; trade-offs |
| [RETRIEVAL_PIPELINE.md](docs/RETRIEVAL_PIPELINE.md) | Dense + sparse + RRF; why RRF over weighted fusion |
| [RERANKING.md](docs/RERANKING.md) | Bi-encoder vs cross-encoder; bge-reranker-base |
| [CITATION_VERIFICATION.md](docs/CITATION_VERIFICATION.md) | Claim extraction, support checking, hallucination surfacing |
| [EVALUATION.md](docs/EVALUATION.md) | Dataset, metrics, ECE, comparison reports |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Every endpoint with schemas + curl examples |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker Compose, env, scaling, local dev |
| [FUTURE_WORK.md](docs/FUTURE_WORK.md) | Roadmap: ColBERT, HyDE, agentic retrieval, CI gates |

---

## Local development (without Docker)

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

> Backend boots even with no Postgres / Qdrant / OpenAI key — it degrades to offline fallbacks. Run `pytest` in `backend/` for the test suite (85 tests, fully offline).

---

## Tech decisions, justified

- **Qdrant over pgvector** — purpose-built ANN, payload filtering, horizontal scaling; keeps vector workload off the OLTP database.
- **RRF over weighted-score fusion** — rank-based fusion is score-scale agnostic, so dense cosine and BM25 magnitudes combine without brittle normalization. See [RETRIEVAL_PIPELINE.md](docs/RETRIEVAL_PIPELINE.md).
- **Cross-encoder rerank after fusion** — a bi-encoder retrieves cheaply at scale; the expensive cross-encoder only scores ~20 fused candidates, buying precision where it counts. See [RERANKING.md](docs/RERANKING.md).
- **Post-hoc citation verification** — generation grounding is necessary but not sufficient; verifying each claim against its cited chunk is what turns "looks cited" into "is supported."
- **Everything is configurable + logged** — chunking strategy, fusion weights, top-k, and prompt version are env/DB-driven so they can be A/B compared by the evaluation harness.

---

## License

MIT — built as a portfolio demonstration of production AI-engineering practices.
