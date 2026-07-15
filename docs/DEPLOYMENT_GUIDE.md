# Deployment Guide — Recall (Hybrid RAG Platform)

This guide covers a production cloud deployment:

| Tier | Platform | Why |
|---|---|---|
| Frontend (React SPA) | **Vercel** | Zero-config Vite builds, global CDN, instant rollbacks. |
| Backend (FastAPI) | **Railway** | Managed Python service + managed Postgres in one project; `$PORT` injection. |
| Vector store | **Qdrant Cloud** | Managed ANN with TLS + API-key auth. |
| Relational store | **Railway Postgres** (or Neon) | Metadata, chunks, query logs, eval runs. |

For a local/demo deployment, use Docker Compose instead — see the [README](../README.md) Quick Start.

> **Config files already in the repo:** [`backend/railway.json`](../backend/railway.json) (Railway build/start/healthcheck), [`frontend/vercel.json`](../frontend/vercel.json) (Vite build + SPA rewrites), [`.env.example`](../.env.example) (full variable surface).

---

## Architecture (deployed)

```
 Browser ──▶ Vercel (static SPA)
                │  fetch  https://<backend>.up.railway.app/v1/*   (VITE_API_BASE)
                ▼
        Railway: FastAPI service ──▶ Railway Postgres   (DATABASE via POSTGRES_* )
                │                 └──▶ Qdrant Cloud      (QDRANT_URL + QDRANT_API_KEY)
                └── Anthropic API  (ANTHROPIC_API_KEY)
```

CORS defaults to open (`ALLOWED_ORIGINS=*`) for the local/demo stack. Before real exposure, set `ALLOWED_ORIGINS` to the Vercel origin; per-IP rate limiting is on by default (see [Production considerations](#production-considerations)).

---

## 1. Qdrant Cloud (do this first — the backend needs it)

1. Create a free cluster at <https://cloud.qdrant.io>.
2. Copy the **cluster URL** (e.g. `https://xxxxxxxx.eu-central.aws.cloud.qdrant.io:6333`) and an **API key**.
3. You'll set these on the backend as `QDRANT_URL` and `QDRANT_API_KEY`. When `QDRANT_URL` is set, the app connects over TLS with auth and ignores `QDRANT_HOST`/`QDRANT_PORT` (see [`vector_store.py`](../backend/app/services/vector_store.py)).
4. The collection (`rag_chunks`) is created automatically on first boot at `EMBEDDING_DIM`. **The startup guardrail will refuse to boot if `EMBEDDING_DIM` ≠ the active embedding model's dimension or ≠ an existing collection's dimension** — so pick your embedding provider before first ingest.

---

## 2. Backend on Railway

### 2.1 Create the service

1. New Project → **Deploy from GitHub repo** → select this repo.
2. In the service **Settings → Root Directory**, set `backend`. Railway's Nixpacks builder detects `requirements.txt`; [`backend/railway.json`](../backend/railway.json) supplies the start command and healthcheck:
   ```
   startCommand:   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   healthcheckPath: /health        # liveness (always 200); /v1/health is deep readiness
   ```
3. Add the **Postgres** plugin to the project (Railway provisions it and exposes connection variables).

### 2.2 Environment variables

Set these on the backend service (Settings → Variables):

| Variable | Value | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | Enables fail-fast startup validation. |
| `LLM_PROVIDER` | `anthropic` | Default provider. |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | **Required** for live answers; without it, production boot fails (no silent downgrade). |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Optional override. |
| `EMBEDDING_PROVIDER` | `openai` *(or `bge` for no-key, 384-dim)* | Pick before first ingest. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Must match `EMBEDDING_DIM`. |
| `EMBEDDING_DIM` | `1536` *(bge-small = `384`)* | Guardrail enforces this vs model + collection. |
| `OPENAI_API_KEY` | `sk-...` | Needed if `EMBEDDING_PROVIDER=openai`. |
| `QDRANT_URL` | `https://...:6333` | From step 1. |
| `QDRANT_API_KEY` | *(key)* | From step 1. |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | from Railway Postgres plugin | Map the plugin's `PG*` values, or reference them with `${{Postgres.PGHOST}}` etc. |

> **Embedding choice tip:** `EMBEDDING_PROVIDER=bge` needs no API key (runs `BAAI/bge-small-en-v1.5` on CPU, 384-dim) — set `EMBEDDING_DIM=384`. Use it to avoid an OpenAI dependency, at the cost of a larger image and slower cold start.

### 2.3 First deploy + seed

After the service is green:

```bash
# From a Railway shell on the backend service (or any env with the same vars):
python scripts/seed_sample_data.py          # ingest the bundled corpus
curl https://<backend>.up.railway.app/v1/providers   # confirm active=anthropic
curl https://<backend>.up.railway.app/v1/health      # expect status: ok
```

`/v1/providers` should report `"llm": { "active": "anthropic" }`. If it shows `"active": "local"`, the key is missing/invalid — in production the service would have failed to boot, so check the deploy logs for the startup error.

---

## 3. Frontend on Vercel

1. New Project → import this repo → set **Root Directory** to `frontend`. Vercel detects Vite; [`frontend/vercel.json`](../frontend/vercel.json) sets the build output and SPA rewrites (so client-side routes don't 404).
2. **Environment variable:**
   | Variable | Value |
   |---|---|
   | `VITE_API_BASE` | `https://<backend>.up.railway.app/v1` |

   The SPA reads this at build time ([`api.ts`](../frontend/src/lib/api.ts)); it defaults to `http://localhost:8000/v1` for local dev.
3. Deploy. Visit the Vercel URL → **System Status** page should show the live backend health and the active providers.

---

## 4. Smoke test the deployment

```bash
BACKEND=https://<backend>.up.railway.app

curl -s $BACKEND/v1/health    | jq '.status, .checks'
curl -s $BACKEND/v1/providers | jq '.llm.active, .embedding.active'
curl -s $BACKEND/v1/metrics   | jq '.queries'
curl -s -X POST $BACKEND/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the PTO policy?","include_trace":false}' | jq '.answer, .confidence.score'
```

Expected: health `ok`, providers `anthropic` / `openai` (or your choices), and an answer with `[n]` citations.

---

## 5. Scaling notes

| Concern | Today | At scale |
|---|---|---|
| **Backend replicas** | Single Railway instance. | Railway horizontal replicas are fine for the API, but two in-process components are per-instance: the **BM25 sparse index** and the **metrics registry**. |
| **BM25 sparse index** | In-process, rebuilt from Postgres. | Multiple replicas each hold their own copy → consistent but memory-duplicated. Move to OpenSearch or Qdrant sparse vectors for shared, horizontally-scalable sparse retrieval. |
| **Metrics** | In-process rolling window (resets on restart, per-replica). | Export to Prometheus/OpenTelemetry; aggregate centrally. |
| **Embeddings/reranker** | OpenAI API (stateless) or local CPU models. | Local `sentence-transformers`/reranker are CPU-bound — give the backend adequate CPU/memory, or use API-based embeddings to keep the image light. |
| **Qdrant** | Single managed cluster. | Qdrant Cloud scales vertically/with sharding; payload-indexed filters keep query latency bounded. |
| **Postgres** | Single instance. | Add read replicas for the analytics/eval read path; the OLTP write path is light (one row per query). |

---

## 6. Production considerations

- **CORS.** Origins are env-driven via `ALLOWED_ORIGINS` (comma-separated) — no code change needed. It defaults to `*`; set it to the Vercel origin(s) in production, e.g. `ALLOWED_ORIGINS=https://recall.vercel.app`. When it is not `*`, credentialed requests are enabled (the CORS spec forbids credentials with a wildcard origin). Implemented in [`main.py`](../backend/app/main.py) / [`config.py`](../backend/app/core/config.py).
- **Rate limiting.** Per-client-IP limiting is on by default — a small pure-ASGI middleware on the [`limits`](https://limits.readthedocs.io) library (see [`ratelimit.py`](../backend/app/core/ratelimit.py)): a global `RATE_LIMIT_DEFAULT` (200/min) on all routes, a stricter `RATE_LIMIT_ASK` (15/min) on the LLM-spend endpoints (`/v1/ask`, `/v1/ask/stream`), and the liveness `/health` exempt so platform healthchecks are never throttled. Over-limit requests get `429` with a `Retry-After` header; allowed requests carry `RateLimit-Limit/Remaining/Reset`. Behind Railway/Vercel the client IP is read from `X-Forwarded-For`. Tune via env or set `RATE_LIMIT_ENABLED=false` to disable. Limits are in-process (per replica); for shared limits across replicas, point `limits` at a Redis/Memcached storage backend instead of the in-memory store.
- **Auth.** There is still no request auth (documented limitation). Rate limiting curbs anonymous abuse, but add an API key / JWT gateway before exposing write/ingest endpoints to untrusted users.
- **Secrets.** All keys are env-only and never logged; `/v1/providers` reports key *presence*, never values. Keep `.env` out of git (already in `.gitignore`).
- **Startup validation.** With `ENVIRONMENT=production`, the service intentionally **fails to boot** on a missing provider key or an embedding-dimension mismatch — this is a feature (no silent quality degradation). Read the deploy log's `startup:` lines if a deploy won't go green.
- **Cost controls.** Per-query cost is tracked from live provider pricing and surfaced in `/v1/metrics` and analytics. Set provider-side spend limits as a backstop.
- **Healthchecks.** Use `/health` (liveness, always 200 when the process is up) for the platform healthcheck; use `/v1/health` (deep readiness: DB + vector store + provider + retrieval, 503 when a required dep is down) for uptime monitoring and dashboards.
- **Embedding immutability.** Changing `EMBEDDING_PROVIDER`/`EMBEDDING_DIM` after ingest invalidates the Qdrant collection. The guardrail blocks the mismatch; to switch, create a new collection (new `QDRANT_COLLECTION` name) and re-ingest.

---

## 7. Rollback

- **Frontend:** Vercel → Deployments → promote a previous deployment (instant).
- **Backend:** Railway → Deployments → redeploy a prior build.
- **Data:** Qdrant Cloud + Postgres are durable across backend redeploys; a rollback of the app does not touch indexed vectors or logged data.
