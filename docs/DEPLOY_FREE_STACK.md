# Deploying Recall on free infrastructure

A complete, publicly reachable deployment at **$0/month hosting**, using the free tiers of four
providers. Written 2026-08-05; free-tier limits change, so confirm current terms as you go.

```
  Browser
     │
     ▼
  Vercel (free)            ← React SPA, static build
     │  https://<space>.hf.space/v1
     ▼
  HF Spaces (free CPU)     ← FastAPI + torch + baked model weights
     ├── Neon (free)       ← Postgres: documents, chunks, queries, evaluations
     └── Qdrant Cloud (free) ← dense vectors
```

## Cost

**Chosen configuration: free hosting, Anthropic for generation.**

All four hosting providers above have genuine free tiers with no card required. The only spend is
LLM calls, on existing Anthropic credit — roughly $0.003/query, so a hundred demo queries costs
well under $1. Set a spend cap on the API key anyway; the endpoint is public.

Embeddings stay free via `EMBEDDING_PROVIDER=bge`, which runs `bge-small-en-v1.5` in-process from
weights baked into the image. No embedding API calls, no key.

`LLM_PROVIDER=local` exists as a zero-spend fallback and keeps the whole pipeline running, but it
answers with a deterministic extractive generator — fine for CI and offline dev, not for a demo
a reviewer will judge you on.

## Known limitations of this stack

- **Cold starts.** Free Spaces sleep after inactivity. A first visit after a sleep waits through
  a container boot — tens of seconds. Acceptable for a résumé link; not for a live interview
  demo, where you should wake it first.
- **Ephemeral disk.** Space storage does not survive a restart. This is fine here: chunks and
  vectors live in Neon and Qdrant Cloud, and only the raw/processed file copies are lost. Set the
  storage dirs under `/tmp` (below) — that is world-writable, so it works regardless of which UID
  the Space runs the container as.
- **Neon free tier scales to zero**, adding a few hundred ms to the first query after idle.

---

## 1. Qdrant Cloud

1. Create a free cluster (1 GB, no card).
2. Copy the cluster URL and create an API key.
3. Keep both for `QDRANT_URL` / `QDRANT_API_KEY`. `QDRANT_URL` takes precedence over
   `QDRANT_HOST`/`QDRANT_PORT` and connects over TLS with auth.

**Dimension must match your embedding provider.** `EMBEDDING_PROVIDER=bge` is 384-dim, OpenAI
`text-embedding-3-small` is 1536. Startup validation aborts on a mismatch rather than silently
writing garbage vectors, so set `EMBEDDING_DIM` correctly. If you switch providers later you must
recreate the collection — the dimension is fixed at creation.

## 2. Neon Postgres

1. Create a free project.
2. Copy the connection string. It looks like
   `postgresql://user:pass@ep-xxx.aws.neon.tech/dbname?sslmode=require`.
3. Paste it verbatim as `DATABASE_URL`. Do not hand-convert the scheme — a bare `postgres://` or
   `postgresql://` is rewritten to `postgresql+psycopg://` automatically, and the `?sslmode=require`
   query arg is preserved. Neon requires SSL, so keep that arg.

`DATABASE_URL` overrides every `POSTGRES_*` value.

## 3. Hugging Face Space

Create a Space with **SDK = Docker**, then push this repo's `backend/` directory as the Space root:

```bash
git remote add hf https://huggingface.co/spaces/<user>/<space-name>
git subtree push --prefix backend hf main
```

`backend/` is self-contained — `Dockerfile`, `app/`, `requirements.txt`, `tests/` — and
`backend/README.md` carries the Space frontmatter (`sdk: docker`, `app_port: 8000`). Pushing the
subtree lands both files at the Space root, which is where Spaces looks for them.

The build takes roughly 10–15 minutes: torch, then ~1.2 GB of model weights. Subsequent pushes
reuse cached layers unless `requirements.txt` changes.

### Space secrets

Set these in **Settings → Variables and secrets**. Anything holding a credential goes in
*Secrets*, not *Variables*.

| Name | Value | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | Enables fail-fast startup validation and redacts raw exception strings from `/health`. Without it you leak driver errors publicly. |
| `LLM_PROVIDER` | `anthropic` | Or `local` for zero spend and weaker answers. |
| `ANTHROPIC_API_KEY` | *secret* | Omit only if `LLM_PROVIDER=local`. |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | |
| `EMBEDDING_PROVIDER` | `bge` | Keyless, in-process, weights baked into the image. |
| `EMBEDDING_DIM` | `384` | Must match `bge-small-en-v1.5`. Mismatch aborts startup. |
| `DATABASE_URL` | *secret* | Neon string from step 2. |
| `QDRANT_URL` | *secret* | Step 1. |
| `QDRANT_API_KEY` | *secret* | Step 1. |
| `ALLOWED_ORIGINS` | `https://<your-app>.vercel.app` | Set after step 4. Leaving `*` lets any site call your API. |
| `ADMIN_API_KEY` | *secret*, any long random string | **Do not skip.** Unset means ingest, delete-document and delete-corpus are open to the internet — anyone could wipe your demo corpus. |
| `RAW_STORAGE_DIR` | `/tmp/recall/raw` | `/tmp` is world-writable, avoiding Space UID permission errors. |
| `PROCESSED_STORAGE_DIR` | `/tmp/recall/processed` | Same. |

Verify: `https://<user>-<space>.hf.space/health` → `{"status":"ok",...}`, and
`/v1/health` for the full dependency report (DB, vector store, provider, retrieval).

## 4. Vercel frontend

1. Import the repo, set **Root Directory** to `frontend/`. `frontend/vercel.json` handles the
   rest (Vite build, SPA rewrites).
2. Set env var `VITE_API_BASE` = `https://<user>-<space>.hf.space/v1`.

`VITE_API_BASE` is read at **build** time, not runtime — set it before the first build, and
redeploy after any change or it silently keeps the old value. Without it the bundle falls back to
`http://localhost:8000/v1`, pointing every visitor's browser at their own machine.

3. Go back and set `ALLOWED_ORIGINS` on the Space to the Vercel URL, then restart the Space.

## 5. Seed the corpus

Ingestion is admin-guarded once `ADMIN_API_KEY` is set:

```bash
curl -X POST https://<user>-<space>.hf.space/v1/ingest \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -F "file=@sample_data/raw/architecture_overview.md"
```

Note the route is `/v1/ingest`, while listing and deletion live under `/v1/documents`. Optional
`?strategy=fixed|recursive|semantic` overrides the configured chunker. Uploads are capped at
`MAX_UPLOAD_BYTES` (10 MiB default) and return 413 above it.

Repeat for the files in `sample_data/raw/`. Then confirm end to end:

```bash
curl -X POST https://<user>-<space>.hf.space/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the incident escalation path?"}'
```

Check the response carries citations and a confidence score, and that `/v1/metrics` increments.

---

## Post-deploy checklist

- [ ] `/health` returns 200; `/v1/health` reports all checks passing
- [ ] `/v1/providers` shows your LLM and embedding providers `active`, not `fallback`
- [ ] A query returns real citations, not the extractive fallback
- [ ] `ALLOWED_ORIGINS` is the Vercel domain, not `*`
- [ ] `POST /v1/ingest` without `X-Admin-Key` returns 401
- [ ] Frontend loads and queries the Space, not localhost
- [ ] Add the live URL to `README.md` — the point of the exercise

## Switching to Railway later

The same image runs on Railway unchanged: `backend/railway.json` already specifies the Dockerfile
builder. You would swap Neon for a Railway Postgres addon and keep Qdrant Cloud. Expect roughly
$25–40/month, driven by the ~2–2.5 GB steady-state RAM the cross-encoder needs. The tradeoff you
are buying is no cold starts.
