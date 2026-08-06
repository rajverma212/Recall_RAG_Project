---
title: Recall — Hybrid RAG API
emoji: 🔎
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
short_description: Hybrid-retrieval RAG API with reranking and verifiable citations
---

# Recall — backend

FastAPI service for the [Recall](https://github.com/rajverma212/Recall_RAG_Project) hybrid RAG
platform: hybrid retrieval (dense + BM25 → RRF), cross-encoder reranking, citation verification,
hallucination detection, and evaluation.

## Why this file has YAML frontmatter

The block above is Hugging Face Spaces configuration. The Space is deployed by pushing **this
directory** as the Space repository root, which puts `Dockerfile` and this `README.md` exactly
where Spaces expects them:

```bash
git subtree push --prefix backend hf main
```

`app_port: 8000` matches the port `uvicorn` binds in the Dockerfile. Spaces routes external
traffic to that port only. The frontmatter is inert outside Spaces — it does not affect local
Docker or Railway.

Full deployment steps, including the free-tier data services this depends on, are in
[docs/DEPLOY_FREE_STACK.md](../docs/DEPLOY_FREE_STACK.md).

## Running locally

From the repository root:

```bash
docker compose up -d
```

API docs at http://localhost:8000/docs, health at http://localhost:8000/v1/health.

## Tests

```bash
cd backend && pytest -q      # 121 tests, fully offline — no keys or services required
```
