# Deployment

## Overview

The platform ships as a four-service Docker Compose stack. A single command builds all images and starts the full system including the database, vector store, backend API, and frontend. Every configuration value is injected via environment variables from a `.env` file; no source edits are required to change runtime behaviour.

---

## Service Architecture

```
┌───────────────────────────────────────────────────────────┐
│                     Docker Compose                         │
│                                                            │
│  ┌──────────────┐    ┌──────────────┐                     │
│  │  postgres    │    │   qdrant     │                     │
│  │  16-alpine   │    │  v1.12.4     │                     │
│  │  :5432       │    │  :6333 HTTP  │                     │
│  │  pgdata vol  │    │  :6334 gRPC  │                     │
│  └──────┬───────┘    │  qdrantdata  │                     │
│         │            └──────┬───────┘                     │
│         │ depends_on        │ depends_on                  │
│         └─────────┬─────────┘                             │
│                   ▼                                        │
│         ┌─────────────────┐                               │
│         │    backend      │                               │
│         │  FastAPI :8000  │                               │
│         │  /data volume   │                               │
│         │  (raw+processed │                               │
│         │  + HF cache)    │                               │
│         └────────┬────────┘                               │
│                  │ proxied via nginx /v1                   │
│         ┌────────▼────────┐                               │
│         │   frontend      │                               │
│         │  nginx :80      │                               │
│         │  (Vite build    │                               │
│         │   served :5173) │                               │
│         └─────────────────┘                               │
└───────────────────────────────────────────────────────────┘
```

---

## Services Reference

| Service | Image | Internal Port | External Port | Volume |
|---|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 | 5432 | `pgdata` |
| `qdrant` | `qdrant/qdrant:v1.12.4` | 6333, 6334 | 6333, 6334 | `qdrantdata` |
| `backend` | Custom (FastAPI) | 8000 | 8000 | `ragdata` → `/data` |
| `frontend` | Custom (nginx) | 80 | 5173 | — |

### Volume descriptions

| Volume | Contents |
|---|---|
| `pgdata` | PostgreSQL data directory (documents, chunks, queries, eval results) |
| `qdrantdata` | Qdrant collection data (vector index + payload) |
| `ragdata` | Raw uploaded files, processed artefacts, HuggingFace model cache |

### Health checks

Both `postgres` and `qdrant` have health checks defined. The `backend` service uses `depends_on: condition: service_healthy` for both, ensuring the backend does not start until the database and vector store are ready. This eliminates race-condition failures on cold starts.

---

## Quickstart

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- (Optional) `OPENAI_API_KEY` for LLM generation and citation verification

### Steps

```bash
# 1. Clone the repository
git clone <repo-url>
cd RAG_Resume_Project

# 2. Copy environment template
cp .env.example .env

# 3. Edit .env — at minimum set OPENAI_API_KEY if desired
#    (system runs fully offline without it)

# 4. Build and start all services
docker compose up --build

# 5. Open the UI
open http://localhost:5173

# 6. Access the API directly
curl http://localhost:8000/v1/documents
```

The first build downloads base images and the BAAI/bge-reranker-base weights into the `ragdata` volume. Subsequent starts reuse the cache and launch in seconds.

---

## Environment Variables

Copy `.env.example` to `.env` and override as needed. All variables are optional except as noted.

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI key. If unset, system runs in full offline mode |
| `POSTGRES_USER` | `raguser` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `ragpassword` | PostgreSQL password |
| `POSTGRES_DB` | `ragdb` | PostgreSQL database name |
| `POSTGRES_HOST` | `postgres` | PostgreSQL host (use service name in Compose) |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `CHUNKING_STRATEGY` | `recursive` | `fixed` \| `recursive` \| `semantic` |
| `CHUNK_SIZE` | `512` | Chunk size in tokens |
| `CHUNK_OVERLAP` | `64` | Overlap between adjacent chunks in tokens |
| `DENSE_TOP_K` | `20` | Candidates returned by DenseRetriever |
| `SPARSE_TOP_K` | `20` | Candidates returned by BM25Retriever |
| `RRF_K` | `60` | RRF rank dampening constant |
| `DENSE_WEIGHT` | `1.0` | RRF weight for dense retriever |
| `SPARSE_WEIGHT` | `1.0` | RRF weight for BM25 retriever |
| `FUSION_TOP_K` | `20` | Candidates after RRF fusion |
| `RERANK_TOP_K` | `5` | Chunks passed to generation after reranking |
| `RERANKER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `GENERATION_MODEL` | `gpt-4o-mini` | OpenAI model for generation |
| `GENERATION_TEMPERATURE` | `0.0` | Sampling temperature (0 = deterministic) |
| `MIN_CONFIDENCE_TO_ANSWER` | `20` | Abstain threshold (0–100) |
| `VITE_API_BASE` | `http://localhost:8000` | Frontend → backend API base URL |

---

## Offline Mode

Setting `OPENAI_API_KEY` to empty or omitting it from `.env` activates full offline mode:

| Component | Online | Offline |
|---|---|---|
| Embedding | `text-embedding-3-small` (OpenAI) | Deterministic hash-based vectors |
| Dense vector store | Qdrant ANN | In-memory NumPy cosine store |
| Generation | `gpt-4o-mini` (OpenAI) | Extractive fallback (top chunks concatenated) |
| Citation verification | LLM judge | Lexical/embedding overlap |
| Reranker | `bge-reranker-base` (local) | Jaccard lexical fallback |

Offline mode is suitable for CI evaluation runs, air-gapped demos, and development without an API key. Retrieval and answer quality degrades significantly compared to the full online stack.

---

## Seeding and Running Evaluation In-Container

### Ingest sample documents

```bash
# From host, upload a file through the API
curl -X POST "http://localhost:8000/v1/ingest" \
  -F "file=@sample_resume.pdf"

# Or exec into the backend container
docker compose exec backend python scripts/seed_corpus.py
```

### Run evaluation

```bash
docker compose exec backend python scripts/run_evaluation.py \
  --name "in_container_baseline" \
  --strategy recursive
```

Reports are written to `evaluation/reports/` inside the `ragdata` volume and are accessible via `docker compose exec backend ls evaluation/reports/`.

---

## Local Development (Non-Docker)

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables (or use a .env file with python-dotenv)
export OPENAI_API_KEY=sk-...
export POSTGRES_HOST=localhost
export POSTGRES_USER=raguser
export POSTGRES_PASSWORD=ragpassword
export POSTGRES_DB=ragdb

# Ensure postgres and qdrant are running (Docker is fine for just these)
docker compose up postgres qdrant -d

# Run migrations
alembic upgrade head

# Start the development server with hot reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Set API base URL
echo "VITE_API_BASE=http://localhost:8000" > .env.local

# Start Vite dev server
npm run dev
# → http://localhost:5173
```

The Vite dev server proxies `/v1` requests to `http://localhost:8000` via its built-in dev proxy, mirroring the nginx configuration in production.

---

## Scaling Notes

The architecture was designed to scale horizontally with minimal restructuring:

### Backend (stateless)

The FastAPI backend is stateless — all persistent state lives in PostgreSQL and Qdrant. Multiple backend replicas can sit behind a load balancer. BM25 state is rebuilt per-request from PostgreSQL chunk data, which is acceptable up to ~50k chunks; beyond this, move BM25 to a dedicated service (see below).

### Qdrant (independent horizontal scaling)

Qdrant v1.12.4 supports distributed mode with sharding and replication. Point the `QDRANT_HOST` env var at a dedicated Qdrant cluster rather than the Compose service. Collection configuration, including embedding dimension (1536) and cosine distance, is preserved.

### BM25 at scale

`rank-bm25` runs entirely in-process. As the corpus grows beyond ~100k chunks, in-memory BM25 becomes a bottleneck (memory pressure + latency). Migration path:

1. **OpenSearch/Elasticsearch** — built-in BM25 with inverted indexes, scales to billions of documents.
2. **Tantivy** (via `tantivy-py`) — Rust-backed in-process full-text search, significantly faster than `rank-bm25` for large corpora.
3. **Hybrid Qdrant** — Qdrant v1.10+ supports sparse vectors natively (BM42 sparse embeddings), allowing BM25-like sparse retrieval via the Qdrant API, removing the need for a separate sparse retriever.

### Database

PostgreSQL 16 handles metadata, chunks, query logs, and evaluation results. For read-heavy analytics workloads, add a read replica. For very large chunk tables, partition by `document_id` or `ingested_at`.

---

## Volume Backup

```bash
# Backup PostgreSQL data
docker run --rm \
  -v ragresume_pgdata:/source \
  -v $(pwd)/backups:/dest \
  alpine tar czf /dest/pgdata_$(date +%Y%m%d).tar.gz -C /source .

# Backup Qdrant data
docker run --rm \
  -v ragresume_qdrantdata:/source \
  -v $(pwd)/backups:/dest \
  alpine tar czf /dest/qdrantdata_$(date +%Y%m%d).tar.gz -C /source .

# Restore PostgreSQL
docker run --rm \
  -v ragresume_pgdata:/dest \
  -v $(pwd)/backups:/source \
  alpine tar xzf /source/pgdata_20260614.tar.gz -C /dest
```

Both volumes must be backed up together for consistency — Qdrant point IDs are referenced by chunk records in PostgreSQL.

---

## Interview Talking Points

- **Why Docker Compose over Kubernetes for this project?** Compose is the right tool for single-node deployment, demos, and local development. The service dependency graph (postgres → qdrant → backend → frontend) is straightforward. Kubernetes adds resource overhead and operational complexity that is not justified until the system needs multi-node horizontal scaling or advanced traffic management.
- **Why nginx for the frontend?** Nginx serves the Vite-built static bundle and proxies `/v1` API calls to the backend, eliminating CORS issues without additional middleware. The same nginx config works in both development (via `docker compose`) and production (behind a cloud load balancer).
- **OPENAI_API_KEY optional:** This was a deliberate design decision. CI runs, offline demos, and air-gapped enterprise deployments all need to function without an API key. The fallback quality is documented so operators understand the trade-off.
- **health-check dependency chain:** Without the `depends_on: condition: service_healthy` pattern, the backend can attempt to connect to PostgreSQL before the cluster is ready, causing startup failures on slow hosts. Health checks add 3–5 seconds to cold start time but eliminate a whole class of flaky startup bugs.
- **HF model cache in ragdata volume:** The BAAI/bge-reranker-base weights (~1.1 GB) are downloaded on first run and persisted in the `ragdata` volume at `/data/hf_cache`. Subsequent restarts reuse the cached weights, keeping cold-start time under 10 seconds.
