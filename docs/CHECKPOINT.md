# Session Checkpoint — Resume Here

**Updated:** 2026-08-03
**Branch:** `main`
**HEAD:** `33f41d9` — `chore: untrack runtime ingestion artifacts from sample_data`
**Git state:** ✅ Working tree clean · ✅ `main == origin/main` · ✅ No stashes. **Nothing to push.**
**Remote:** `git@github.com:rajverma212/Recall_RAG_Project.git`

---

## TL;DR for resuming

The `production-hardening` branch was merged into `main` and three further passes landed on top
(frontend clarity → security/confidence hardening → repo cleanup). Everything is committed and
pushed. No work is in flight.

**The platform runs correctly but is not deployed anywhere.** That is the single biggest gap
between where this is and a finished portfolio piece. See [Path to live](#path-to-live-ordered).

Both **P0 deploy blockers are now fixed and verified** (Railway builder + baked reranker weights).
The remaining items are P1/P2 — configuration and polish, not blockers. Next concrete step is
provisioning Railway + Qdrant Cloud and setting the production env vars.

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

### P1 — Image size is 4.75 GB
Up from 2.61 GB; 1.13 GB of that is the intentional weights bake. Large images deploy slowly and
can bump Railway plan limits. Easiest win: a multi-stage build dropping `build-essential`
(324 MB), which is only needed to compile wheels during install. The pip layer is 1.56 GB.

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
