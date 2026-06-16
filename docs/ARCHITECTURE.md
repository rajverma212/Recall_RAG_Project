# Architecture

This document explains the system design of the Hybrid RAG Platform: its components, data flow, data model, and the rationale behind each major decision. It is written to double as a system-design interview reference.

---

## 1. Design goals

1. **Trustworthy answers.** Every factual statement must be traceable to a source chunk and verified against it. Unsupported claims are flagged, not hidden.
2. **Retrieval quality over cleverness.** Hybrid dense+sparse retrieval with reranking beats single-method retrieval on heterogeneous internal docs.
3. **Measurable.** Nothing ships without an evaluation number. Chunking, fusion weights, and prompts are all swappable and benchmarkable.
4. **Operable.** One-command startup, cost/latency tracking, health checks, and graceful degradation when an external dependency is missing.
5. **Portfolio-legible.** A reviewer can read the docs, run `docker compose up`, and see the whole pipeline working in minutes.

---

## 2. Component overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Frontend (React + TS + Vite + Tailwind + TanStack Query)                  │
│  Ask · Retrieval Inspector · Evaluation · Documents · Analytics · Exps     │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ HTTP / SSE  (nginx proxies /v1 → backend)
┌────────────────────────────────▼─────────────────────────────────────────┐
│ Backend (FastAPI + Pydantic v2)                                           │
│                                                                            │
│  api/v1/         ask · documents · evaluations · analytics · experiments  │
│       │                                                                    │
│  services/       RAGService          IngestionService                      │
│       │                │                    │                              │
│  retrieval/   dense · bm25 · fusion · reranker · pipeline                  │
│  generation/  prompts · generator                                          │
│  verification/ citations · verifier · confidence                          │
│  ingestion/   loaders · detect · dedup                                     │
│  chunking/    fixed · recursive · semantic                                 │
│  evaluation/  metrics · runner · report                                    │
│       │                                                                    │
│  services/embeddings.py   services/vector_store.py   (shared adapters)      │
└──────────┬──────────────────────────────┬────────────────────────────────┘
           │                              │
   ┌───────▼────────┐            ┌────────▼────────┐         ┌──────────────┐
   │  PostgreSQL    │            │     Qdrant      │         │  OpenAI API   │
   │  documents     │            │  rag_chunks     │         │  embeddings   │
   │  chunks        │            │  (1536-d cosine)│         │  + chat       │
   │  query_logs    │            └─────────────────┘         │  (optional)   │
   │  evaluation_*  │                                        └──────────────┘
   │  experiments   │
   │  prompt_versions│
   └────────────────┘
```

### Layering

- **API layer** (`app/api/v1/`) — thin HTTP handlers. Validate with Pydantic, call a service, return a schema. No business logic.
- **Service layer** (`app/services/rag_service.py`, `ingestion_service.py`) — orchestrates the pipelines and owns transactions. These are the two seams the rest of the system is built around.
- **Domain modules** (`retrieval/`, `generation/`, `verification/`, `ingestion/`, `chunking/`) — single-responsibility units, each independently testable.
- **Adapters** (`services/embeddings.py`, `services/vector_store.py`) — wrap OpenAI and Qdrant so no domain code imports a vendor SDK directly. Both expose an offline fallback.

> **Design rationale:** keeping the API thin and centralising orchestration in two service classes means the same pipelines are reused by the HTTP routes *and* the evaluation runner *and* the seed scripts — there is exactly one code path for "ask a question," so evaluation measures what production runs.

---

## 3. Request flow: `POST /v1/ask`

```
1. AskRequest validated (question, stream?, include_trace?, prompt_version?, experiment_id?)
2. RAGService.ask():
   a. Resolve system prompt  ← PromptVersion (req.prompt_version | active | default)
   b. HybridRetriever.retrieve(db, query):
        dense  = DenseRetriever  → embed query → Qdrant search (top-20)
        sparse = Bm25Retriever   → BM25Okapi over chunk text (top-20)
        fused  = reciprocal_rank_fusion(dense, sparse, k=60, weights)   (top-20)
        final  = Reranker(bge-reranker-base).rerank(query, fused) (top-5)
        → returns (context_chunks, RetrievalTrace{dense,bm25,rrf,reranked})
   c. format_context(context_chunks)  → numbered [1..5] block
   d. Generator.generate(system_prompt, context, question)  → answer + token usage
   e. extract_citations(answer, context)        → [n] → chunk + supporting quote
   f. verify(answer, citations, context)         → per-claim supported/partial/unsupported
   g. compute_confidence(...)                    → 0–100 + breakdown
   h. cost = tokens × price;  persist QueryLog
3. Return AskResponse (answer, citations, verifications, confidence, trace, cost, latency)
```

The streaming variant (`POST /v1/ask/stream`, Server-Sent Events) runs retrieval first, streams generation tokens as `{"type":"token"}` events, then emits a final `{"type":"done","data": AskResponse}` after verification + scoring.

---

## 4. Ingestion flow: `POST /v1/ingest`

```
detect_doc_type(filename, content_type)            → pdf | markdown | html | txt
sha256(raw_bytes)  → if a completed doc matches → return (idempotent, no re-work)
write raw bytes → {RAW_STORAGE_DIR}/{doc_id}_{filename}     (raw is preserved as-is)
Document(status=processing)  persisted
get_loader(doc_type).load(raw)   → [LoadedSection] (text + page/section/heading meta)
get_chunker(strategy).chunk(sections)  → [ChunkPiece] (token-counted, metadata-carrying)
embed all chunk texts (batched)
Deduplicator: cosine ≥ 0.95 vs in-batch + already-indexed → mark duplicates, skip+log
persist Chunk rows (provenance + chunking metadata); upsert non-dup vectors → Qdrant
write processed chunks → {PROCESSED_STORAGE_DIR}/{doc_id}.json
Document(status=completed, num_chunks, num_pages, title)
```

On any exception the document is marked `failed` with the error string, and the transaction is rolled back — partial ingests never pollute the index.

> **Why separate raw and processed storage?** Raw files are the immutable source of truth — re-chunking with a new strategy or fixing a loader bug must not require re-uploading. Processed JSON is a derived, regenerable artifact.

---

## 5. Data model (PostgreSQL)

| Table | Purpose | Key columns |
|---|---|---|
| `documents` | one row per ingested file | `sha256` (idempotency), `doc_type`, `status`, `raw_path`, `num_chunks`, `chunking_strategy` |
| `chunks` | one row per processed chunk (source of truth for text) | `text`, `source_file`, `page_number`, `section_title`, `heading_path`, `strategy`, `chunk_size`, `chunk_overlap`, `is_duplicate`, `duplicate_of`, `dedup_similarity`, `embedded` |
| `query_logs` | analytics + audit for every `/ask` | `question`, `answer`, `citations` (JSON), `confidence`, `citation_accuracy`, token counts, `cost_usd`, `latency_ms`, `prompt_version`, `experiment_id` |
| `evaluation_runs` | one row per evaluation run | snapshot `config` (JSON) + aggregate metrics |
| `evaluation_results` | per-example result | `category`, `metrics` (JSON), `passed` |
| `prompt_versions` | prompt versioning | `version`, `system_prompt`, `is_active` |
| `experiments` | experiment tracking | `config` (JSON), `metrics` (JSON), `evaluation_run_id` |

**Postgres holds chunk text + metadata; Qdrant holds only vectors keyed by `chunk_id`.** This keeps a single relational source of truth (easy to re-embed, re-index, or migrate vector stores) while delegating ANN search to the specialised engine. BM25 is rebuilt lazily in-process from the `chunks` table.

---

## 6. Key design decisions & trade-offs

### 6.1 Hybrid retrieval (dense + sparse) instead of dense-only
Dense embeddings capture semantics but miss exact identifiers, rare tokens, error codes, and acronyms common in internal docs. BM25 nails lexical matches but misses paraphrase. Fusing the two covers both failure modes. **Trade-off:** two indexes to maintain and a fusion step; mitigated by rebuilding BM25 lazily from Postgres (no separate store).

### 6.2 Reciprocal Rank Fusion over weighted score fusion
Cosine similarity and BM25 scores live on incompatible scales; normalizing them is brittle and corpus-dependent. RRF (`Σ wᵢ/(k+rankᵢ)`, `k=60`) fuses by **rank**, which is scale-free and robust. Weights (`dense_weight`, `sparse_weight`) still allow tilting toward one method. See [RETRIEVAL_PIPELINE.md](RETRIEVAL_PIPELINE.md).

### 6.3 Cross-encoder rerank as a second stage
Bi-encoders embed query and document independently (fast, scalable, approximate). Cross-encoders jointly attend over (query, document) (accurate, expensive). We retrieve cheaply to ~20 candidates, then spend the cross-encoder only on those, getting precision without scanning the whole corpus. See [RERANKING.md](RERANKING.md).

### 6.4 Verification is post-hoc and separate from generation
Asking the LLM to "only use context and cite" reduces hallucination but does not eliminate it. An independent verifier re-checks each claim against its cited chunk, so trust is *measured*, not assumed. This also powers the citation heatmap and the faithfulness metric.

### 6.5 Graceful degradation everywhere
`embeddings.py`, `vector_store.py`, the reranker, and the generator each have an offline fallback (deterministic hash embeddings, in-memory cosine store, lexical reranker, extractive generator). The platform boots and the full pipeline runs with **no** Postgres/Qdrant/OpenAI — essential for CI, tests, and a frictionless demo. Production simply swaps the real backends in via env vars.

### 6.6 Configuration as a first-class concern
Every knob (chunking strategy, chunk size/overlap, dedup threshold, top-k at each stage, fusion weights, reranker device, prompt version) lives in `app/core/config.py` and is environment-overridable. The evaluation harness exploits this to benchmark configurations against each other.

---

## 7. Failure modes & handling

| Failure | Behaviour |
|---|---|
| OpenAI key absent / API error | Fallback embeddings + extractive generator; pipeline continues |
| Qdrant unreachable | In-memory cosine vector store; warning logged |
| Postgres unreachable (eval/scripts) | Evaluation writes JSON report to `evaluation/reports/`; `/ask` QueryLog write no-ops |
| Reranker model unavailable | FlagEmbedding → CrossEncoder → lexical Jaccard fallback |
| Unsupported file type | `400` with a clear message (loader factory raises `ValueError`) |
| Duplicate document (same sha256) | Idempotent no-op, returns existing chunk count |
| Near-duplicate chunk (≥0.95 cos) | Skipped, logged, recorded with `duplicate_of` + similarity |
| Ingestion exception | Document marked `failed`, transaction rolled back |

---

## 8. Scaling notes

- **Stateless backend** → scale horizontally behind a load balancer; the only in-process state is the lazily-built BM25 index and model singletons (rebuilt per instance).
- **Qdrant** scales independently (sharding/replication) and is the heavy retrieval path.
- **Embeddings/generation** are network-bound; batch embedding and a response/embedding cache are the first optimizations (see [FUTURE_WORK.md](FUTURE_WORK.md)).
- **BM25** is in-process for simplicity; at large corpus sizes move sparse retrieval to OpenSearch/Elasticsearch or Qdrant's native sparse vectors.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the operational view.
