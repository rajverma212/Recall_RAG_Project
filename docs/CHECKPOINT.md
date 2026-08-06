# Session Checkpoint — Resume Here

**Updated:** 2026-08-05
**Branch:** `main`
**Git state:** ✅ Working tree clean · ✅ `main == origin/main` · ✅ No stashes.
**Remote:** `git@github.com:rajverma212/Recall_RAG_Project.git`

---

## TL;DR for resuming

**Decision made: deploy on free hosting, pay only for Anthropic generation.**
Stack = Hugging Face Spaces (backend) + Neon (Postgres) + Qdrant Cloud (vectors) + Vercel
(frontend). All four free tiers. Embeddings keyless via `bge-small-en-v1.5` baked into the image.
Full runbook with the env-var manifest: **[DEPLOY_FREE_STACK.md](DEPLOY_FREE_STACK.md)** — that
is the document to open first next session.

Both **P0 deploy blockers are fixed and verified**; the code side of deployment is done. What
remains is provisioning, which needs your accounts:

1. Create the Qdrant Cloud free cluster → `QDRANT_URL` + `QDRANT_API_KEY`
2. Create the Neon project → `DATABASE_URL`
3. Create the HF Space (SDK = Docker), `git subtree push --prefix backend hf main`, set secrets
4. Vercel: root dir `frontend/`, set `VITE_API_BASE` to the Space URL **before** first build
5. Pin `ALLOWED_ORIGINS` to the Vercel domain, set `ADMIN_API_KEY`, seed the corpus

The platform still is not deployed anywhere — that remains the single biggest gap between this
and a finished portfolio piece.

---

## What landed since the last checkpoint

### 1. Frontend clarity pass (`49c5b2a`, 2026-07-14)
- Hallucination page: clickable sample-question chips (fill + analyze), "how it works" strip,
  "what you'll see" result-preview panel, concrete placeholder, real loading state.
- Experiments & Prompts: dead-end empty states rewritten to explain what each registry is for.
- Swept in pending backend work: rate limiting ([ratelimit.py](../backend/app/core/ratelimit.py)),
  evaluations API expansion, ingestion updates, deploy docs.

### 2. Security + RAG correctness (`0ccd9e8`, 2026-07-17) — the substantive one
- **Confidence math:** `retrieval_confidence` now normalises against the theoretical RRF max
  `((dense_weight + sparse_weight) / (rrf_k + 1))` instead of the batch's own top score, so a
  single weak chunk no longer scores a bogus 1.0.
  ([confidence.py](../backend/app/verification/confidence.py))
- **Optional admin guard** ([deps.py](../backend/app/api/deps.py)) on ingest, delete-document,
  delete-corpus, evaluation-run, experiment-create. No-op when `ADMIN_API_KEY` is unset (demo
  stays open); requires `X-Admin-Key` when set.
- **Upload cap** (`MAX_UPLOAD_BYTES`, default 10 MiB) with a bounded read → 413.
- **Exception redaction** on `/health` in production.
- **docker-compose:** loopback-bound postgres/qdrant/backend; only the frontend is public. Also
  closed the direct path that made the rate limiter `X-Forwarded-For`-spoofable.
- **Frontend:** `Document.status` mirrors backend `IngestionStatus` (failed ingests render red
  with the error); real `AbortController` so "New query" mid-stream cancels backend generation.
- Verified at the time: **113/113 backend tests**, frontend tsc+build, full Docker stack driven
  end-to-end.

### 3. Repo cleanup (`33f41d9`, 2026-07-23)
- Untracked UUID-prefixed raw copies + processed JSON from `sample_data/` (regenerated on ingest)
  and gitignored them. ~7,400 lines removed. Files remain on disk; original seed docs still tracked.

### 4. Deployment unblocking (2026-08-04 → 08-05)
- `11e0cb2` — both P0 blockers: Railway builder + baked reranker weights (details below).
- `89cd3a2` — multi-stage Dockerfile; build toolchain no longer ships. 4.75 GB → 4.35 GB.
- `f914e56` — `DATABASE_URL` support for managed Postgres. Neon/Supabase issue one connection
  string with `?sslmode=require`, which the discrete `POSTGRES_*` form could not express — there
  was no way to point the app at managed Postgres at all. Bare `postgres://` / `postgresql://`
  schemes are rewritten to `postgresql+psycopg://` (SQLAlchemy maps both to psycopg2, which this
  project does not install). +8 tests; suite now **121 passing**.
- Docs: [DEPLOY_FREE_STACK.md](DEPLOY_FREE_STACK.md) runbook, [backend/README.md](../backend/README.md)
  with HF Space frontmatter.

---

## State of the running stack

Docker Desktop is **not running** as of this checkpoint (`docker compose ps` fails to reach the
daemon). Nothing is up locally.

```bash
docker compose up -d        # image already built; brings up all 4 services
docker compose ps           # check what's up
docker compose down         # stop (keep data volumes)
docker compose down -v      # stop + drop Postgres/Qdrant volumes
```

Endpoints when up: frontend http://localhost:5173 · API docs http://localhost:8000/docs ·
health http://localhost:8000/v1/health

---

## Path to live (ordered)

Findings from a 2026-08-03 audit of the deploy configs against the code. Ordered by what blocks
what — not by effort.

### ~~P0 — Railway will not build the backend correctly~~ ✅ DONE 2026-08-04
`railway.json` set `"builder": "NIXPACKS"`, which ignored the Dockerfile entirely — and that
Dockerfile is where the CPU-only torch pin lives (the `36c785c` fix stopping torch from pulling
~3–5 GB of unused CUDA wheels). Deeper problem: Railway resolves `dockerfilePath` relative to the
service root, and `railway.json` sitting in `backend/` makes that root `backend/`, so
`../docker/backend.Dockerfile` was unreachable *regardless of builder*.
**Fixed:** Dockerfile moved (`git mv`) to [backend/Dockerfile](../backend/Dockerfile) so it lives
inside the build context; compose repointed at it; builder switched to `DOCKERFILE`;
`healthcheckTimeout` 120 → 300 (a cold boot loading a 1.1 GB cross-encoder won't answer in 120s).

### ~~P0 — Reranker model is never baked into the image~~ ✅ DONE 2026-08-04
**Fixed** with a build-time `CrossEncoder(...)` warm-up placed above `COPY . .` so app-code changes
don't invalidate the expensive layer. Two traps found while verifying:
1. **Volume shadowing.** `HF_HOME` was `/data/hf`, but `/data` is the mounted `ragdata` volume.
   Docker only seeds a named volume from image content when the volume is *empty* — an existing
   volume would have hidden the baked weights and sent it back to runtime downloads. `HF_HOME` is
   now `/opt/hf`, outside any mount.
2. **Baking alone was not sufficient.** `huggingface_hub` revalidates a cached model against the
   Hub before loading, so the network stayed on the boot path; a Hub outage or rate-limit would
   still land in the silent lexical-fallback path. Now pinned with `HF_HUB_OFFLINE=1` /
   `TRANSFORMERS_OFFLINE=1`, set *after* the download step.

**Verified:** image builds and exports; weights resident as a 1.13 GB layer; `docker run
--network none` loads the cross-encoder and scores 0.9998 relevant / 0.0 irrelevant — i.e. real
reranking with the network fully removed.

### ~~P1 — Image size~~ ✅ PARTLY ADDRESSED 2026-08-04
Multi-staged the Dockerfile: a `builder` stage compiles wheels and downloads weights, a `runtime`
stage copies forward only `site-packages`, `/usr/local/bin`, and `/opt/hf`. The build toolchain is
discarded. **4.75 GB → 4.35 GB.**

One non-obvious dependency: `libgomp1` must be explicitly installed in the runtime stage. It used
to arrive as a transitive dep of `build-essential`, and without it `import torch` fails with
`libgomp.so.1: cannot open shared object file`.

Still 4.35 GB — the floor is the 1.56 GB pip layer (torch dominates) plus 1.13 GB of weights.
Further reduction would mean dropping dev-only deps (`pytest`, `pytest-xdist`, `deepeval`,
`sentry-sdk`) from the runtime install, worth ~200-400 MB more if deploy size becomes a real
constraint.

**Verified:** torch 2.13.0+cpu (CPU pin survived the stage copy), lxml/psycopg/sklearn/scipy/numpy
all import, `app.main` imports, reranking offline scores 0.9979 relevant / 0.0 irrelevant,
container boots and `/health` returns 200.

### P1 — Frontend cannot reach the backend when split across hosts
[api.ts:19](../frontend/src/lib/api.ts#L19) is
`import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/v1'`. Works under Docker (nginx proxies
`/v1/`) and in dev (Vite proxy), but a Vercel build with no env var points the browser at the
user's own localhost. **Fix:** set `VITE_API_BASE` to the Railway origin in Vercel env.

### P1 — Production env is not pinned
- `ALLOWED_ORIGINS=*` must be pinned to the Vercel domain.
- `ENVIRONMENT=production` must be set, or fail-fast startup validation and `/health` exception
  redaction stay off.
- `ADMIN_API_KEY` must be set. Unset means ingest / delete-corpus / delete-document / eval-run are
  **open to the public internet** — the guard exists precisely for this and is currently a no-op.

### P2 — Managed data services
Railway Postgres addon + Qdrant Cloud (`QDRANT_URL` / `QDRANT_API_KEY` already supported and take
precedence over host/port). Note the backend image was 2.58 GB — plan for a paid Railway tier,
not the free one.

### P2 — Eval gate is currently decorative
CI floors are calibrated to the offline local provider (`EVAL_MIN_ANSWER_CORRECTNESS: "0.15"`).
That gate cannot catch a real regression. Run a keyed Anthropic eval, publish the real numbers,
and raise the floors toward the targets in [FUTURE_WORK.md](FUTURE_WORK.md).

### Known non-blockers
- BM25 index is in-memory, rebuilt from Postgres on a row-count change
  ([bm25.py:110](../backend/app/retrieval/bm25.py#L110)). Fine at one instance; first query after a
  cold start pays the rebuild. Would need rework before horizontal scaling.
- `datetime.utcnow()` deprecation warnings remain (cosmetic).

---

## Push command

```bash
git add -A
git commit -m "your message"
git push                      # main already tracks origin/main
```
