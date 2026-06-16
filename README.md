# Recall

A hybrid-retrieval RAG engine for document Q&A with cited answers.

Recall ingests your documents, indexes them with both dense (vector) and sparse (keyword)
retrieval, reranks the candidates, and generates answers grounded in — and cited back to —
the source chunks.

## Features

- **Hybrid retrieval** — dense vector search + sparse keyword search, with tunable weighting
  (`DENSE_WEIGHT` / `SPARSE_WEIGHT`).
- **Reranking** — candidates are reranked before generation (`RERANK_TOP_K`).
- **Pluggable chunking** — `fixed`, `recursive`, and structure-aware strategies, selectable
  per-ingest or via `CHUNKING_STRATEGY`. See [docs/CHUNKING_STRATEGIES.md](docs/CHUNKING_STRATEGIES.md).
- **Cited answers** — responses link back to the source chunks they were drawn from.
- **Evaluation harness** — measure retrieval and answer quality (`evaluation/`).
- **Runs offline** — leave `OPENAI_API_KEY` blank for deterministic fallback embeddings and a
  stub generator (handy for demos / CI); set a key for full quality.

## Stack

- **Backend** — FastAPI (Python), Postgres + pgvector
- **Frontend** — React + Vite + TypeScript
- **Infra** — Docker Compose

## Quick start

```bash
cp .env.example .env        # optionally add OPENAI_API_KEY
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000/v1

## Configuration

Key knobs (see [.env.example](.env.example) for the full list):

| Variable             | Purpose                                          |
| -------------------- | ------------------------------------------------ |
| `OPENAI_API_KEY`     | LLM/embeddings; blank = offline fallback mode     |
| `CHUNKING_STRATEGY`  | `fixed` \| `recursive` \| structure-aware         |
| `DENSE_WEIGHT`       | Weight of vector search in hybrid scoring         |
| `SPARSE_WEIGHT`      | Weight of keyword search in hybrid scoring         |
| `RERANK_TOP_K`       | How many reranked chunks feed the generator       |

## Documentation

- [Ingestion pipeline](docs/INGESTION_PIPELINE.md)
- [Chunking strategies](docs/CHUNKING_STRATEGIES.md)
