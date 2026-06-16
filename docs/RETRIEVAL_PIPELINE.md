# Retrieval Pipeline

## Overview

This document describes the hybrid retrieval pipeline at the core of the RAG platform. The pipeline combines dense vector search with sparse lexical search, fuses the results using Reciprocal Rank Fusion (RRF), and delivers a ranked shortlist to a cross-encoder reranker before generation. Every stage is configurable via environment variables and falls back gracefully when external services are unavailable.

---

## Architecture Diagram

```
                         ┌─────────────────────────────────────┐
                         │            User Question             │
                         └──────────────────┬──────────────────┘
                                            │
                          ┌─────────────────▼─────────────────┐
                          │         Query Embedding             │
                          │   text-embedding-3-small (1536-d)   │
                          └──────┬──────────────────────┬──────┘
                                 │                      │
               ┌─────────────────▼──┐          ┌───────▼─────────────────┐
               │   DenseRetriever   │          │     BM25Retriever        │
               │  Qdrant ANN search │          │  rank-bm25 BM25Okapi     │
               │  cosine, top-20    │          │  over Postgres chunks    │
               │                    │          │  top-20                  │
               └─────────────────┬──┘          └───────┬─────────────────┘
                                 │                      │
                    ┌────────────▼──────────────────────▼──────────┐
                    │         Reciprocal Rank Fusion (RRF)          │
                    │   score = Σ weight / (k + rank),  k=60        │
                    │   dense_weight=1.0, sparse_weight=1.0         │
                    │   output: top-20 fused candidates             │
                    └────────────────────────┬──────────────────────┘
                                             │
                              ┌──────────────▼──────────────┐
                              │    Cross-Encoder Reranker    │
                              │  BAAI/bge-reranker-base      │
                              │  scores → sigmoid [0,1]      │
                              │  output: top-5               │
                              └──────────────┬───────────────┘
                                             │
                              ┌──────────────▼──────────────┐
                              │         Generation           │
                              │  gpt-4o-mini, T=0.0          │
                              │  grounded system prompt      │
                              └─────────────────────────────┘
```

---

## Stage 1 — Dense Retrieval

### Mechanism

The query is embedded with OpenAI `text-embedding-3-small` (1536 dimensions, cosine similarity) and used to query Qdrant's approximate nearest-neighbour (ANN) index. The retriever fetches the top `dense_top_k` (default 20) candidates.

### Why dense retrieval?

Dense retrieval captures semantic similarity: synonyms, paraphrases, and cross-lingual near-matches all surface naturally because the embedding model learns a continuous semantic space. A query like "compensation" will match chunks containing "salary" or "remuneration" even without lexical overlap.

### Trade-offs

| Aspect | Dense | Sparse (BM25) |
|---|---|---|
| Semantic matching | Excellent | Poor |
| Exact keyword matching | Poor | Excellent |
| Out-of-vocabulary terms | Handles well | Fails |
| Named entities, model numbers | Often misses | Reliable |
| Inference cost | Embedding call | None (in-memory) |
| Index size | O(N × 1536 floats) | Inverted index |

### Offline fallback

When Qdrant is unreachable, an in-memory cosine vector store backed by NumPy is used. When OpenAI is unavailable, embeddings are replaced with deterministic hash-based vectors that preserve partial lexical structure. Both fallbacks degrade quality but preserve system availability.

---

## Stage 2 — Sparse Retrieval (BM25)

### Mechanism

`rank-bm25` implements `BM25Okapi` over the raw chunk texts loaded from PostgreSQL. The query is tokenized and scored against every chunk using the standard BM25 formula.

### BM25Okapi formula

```
BM25(q, d) = Σ_{t∈q} IDF(t) × (TF(t,d) × (k1+1)) / (TF(t,d) + k1 × (1 − b + b × |d|/avgdl))
```

Where:
- `IDF(t) = log((N − df(t) + 0.5) / (df(t) + 0.5) + 1)`
- `k1 = 1.5`, `b = 0.75` (BM25Okapi defaults)

### Small-corpus IDF edge case

On very small corpora (e.g., a single uploaded document), `df(t)` can approach `N`, driving `IDF(t)` toward zero or below. In this situation `BM25Okapi` scores become uninformative (all near-zero). The retriever detects this condition and falls back to **query-token overlap ranking**: chunks are ranked by the count of query tokens they contain. This preserves a useful ordering while avoiding misleading near-zero BM25 scores.

### Why keep BM25 alongside dense?

BM25 reliably retrieves chunks containing rare terms, model names, version numbers, and exact identifiers that dense embeddings blur into the surrounding semantic space. The two signals are complementary, which is exactly what RRF exploits.

---

## Stage 3 — Reciprocal Rank Fusion

### Formula

For each candidate chunk appearing in one or more ranked lists:

```
RRF_score(chunk) = Σ_{r ∈ retrievers} ( weight_r / (k + rank_r(chunk)) )
```

Where:
- `rank_r(chunk)` is the 1-based rank of the chunk in retriever `r` (if absent, the term is omitted)
- `k = 60` (constant that dampens the influence of top-ranked items)
- `weight_r` ∈ {`dense_weight`, `sparse_weight`}, both default `1.0`

The top `fusion_top_k` (default 20) candidates by RRF score advance to the reranker.

### Why RRF over weighted score normalisation?

Score distributions differ fundamentally between retrievers:

| Retriever | Score range | Distribution shape |
|---|---|---|
| Dense (cosine) | [−1, 1] but typically [0.6, 0.95] | Narrow, clustered near top |
| BM25 | [0, ∞) | Skewed, corpus-size dependent |

Normalising these to a common range requires heuristics (min-max per query, global calibration) that are brittle and corpus-dependent. RRF sidesteps normalisation entirely: **it uses only ranks, not scores**. This makes it:

1. **Robust** — a BM25 score of 8.2 and a cosine score of 0.82 are both treated as "rank 3", removing scale incompatibility.
2. **Calibration-free** — no per-query normalisation step needed.
3. **Empirically strong** — RRF was shown by Cormack et al. (2009) to outperform learned combination weights on most fusion benchmarks despite its simplicity.

### Why k = 60?

The `k` constant controls how much the fusion penalises lower ranks. At `k=60`:
- Rank 1 contributes `1/61 ≈ 0.0164`
- Rank 10 contributes `1/70 ≈ 0.0143`
- Rank 60 contributes `1/120 ≈ 0.0083`

This dampening means the top few ranks matter a lot but are not overwhelmingly dominant — a chunk ranked 2nd in both lists often beats a chunk ranked 1st in one list and absent in the other. `k=60` was the value reported in the original RRF paper and has become a stable empirical default across retrieval research. It can be overridden via `rrf_k` if the corpus distribution warrants experimentation.

### Configurable weights

`dense_weight` and `sparse_weight` act as multipliers on the per-retriever term. Setting `dense_weight=2.0` and `sparse_weight=1.0` biases the fusion toward semantic relevance, useful for paraphrase-heavy query sets. Setting `sparse_weight=2.0` favours exact-match corpora (legal text, technical specs). Equal weights (default) are a sensible starting point for general-purpose retrieval.

---

## Per-Stage Configuration Reference

| Parameter | Default | Affects |
|---|---|---|
| `dense_top_k` | 20 | Candidates from DenseRetriever |
| `sparse_top_k` | 20 | Candidates from BM25Retriever |
| `rrf_k` | 60 | RRF rank dampening constant |
| `dense_weight` | 1.0 | RRF weight for dense retriever |
| `sparse_weight` | 1.0 | RRF weight for BM25 retriever |
| `fusion_top_k` | 20 | Candidates sent to reranker |
| `rerank_top_k` | 5 | Final chunks sent to generation |

All values are env-overridable via `.env` or runtime config.

---

## Latency Budget (Approximate, Single Query)

| Stage | Operation | Typical Latency |
|---|---|---|
| Query embedding | OpenAI API call (1536-d) | 80–150 ms |
| Dense retrieval | Qdrant ANN search, top-20 | 5–20 ms |
| BM25 retrieval | In-process rank-bm25 scan | 2–15 ms |
| RRF fusion | Pure Python rank merge | < 1 ms |
| Reranking | Cross-encoder, top-20→5 | 50–200 ms (CPU) |
| Generation | OpenAI chat completion | 800–3000 ms |
| **End-to-end** | | **~1–3.5 s** |

Notes:
- Retrieval stages (dense + sparse + RRF) run concurrently where async permits.
- Reranking dominates non-generation latency; GPU inference cuts it to ~10–30 ms.
- Generation latency dominates overall; streaming (`/ask/stream`) eliminates perceived wait by delivering tokens as they arrive.

---

## Trace Output

Every `/ask` call with `include_trace=true` returns a `trace` object containing per-stage results:

```json
{
  "trace": {
    "dense":    { "name": "dense",   "results": [...], "elapsed_ms": 12 },
    "bm25":     { "name": "bm25",    "results": [...], "elapsed_ms": 6  },
    "rrf":      { "name": "rrf",     "results": [...], "elapsed_ms": 0  },
    "reranked": { "name": "reranked","results": [...], "elapsed_ms": 87 }
  }
}
```

Each `results` array contains `RetrievedChunk` objects with `chunk_id`, `document_id`, `text`, `score`, `source_file`, `page_number`, `section_title`, `heading_path`, and `rank`. This trace is invaluable for debugging retrieval failures and tuning per-stage `top_k` values.

---

## Interview Talking Points

- **Why hybrid?** Neither dense nor sparse dominates universally. BM25 excels at rare terms and exact identifiers; dense retrieval excels at paraphrase and semantic equivalence. Combining them with RRF consistently outperforms either alone across BEIR benchmarks.
- **Why RRF not learned combination?** RRF requires no training data, no score calibration, and no per-corpus tuning. Learned weights overfit to the training distribution and require re-tuning when the corpus changes. RRF is a strong baseline that is genuinely hard to beat without significant engineering investment.
- **k=60 origin:** From Cormack, Clarke & Buettcher (SIGIR 2009). It ensures top-ranked items are rewarded without making the fusion collapse into a winner-take-all regime.
- **BM25 fallback on small corpora:** IDF(t) = log((N − df + 0.5)/(df + 0.5) + 1); when df ≈ N the log approaches 0. We detect this and switch to overlap ranking so the retriever stays useful even on a corpus of one document.
- **Offline resilience:** The system stays available without OpenAI (hash embeddings + in-memory store) and without Qdrant (NumPy cosine fallback). This is critical for demos and CI environments.
- **Tuning levers:** `dense_weight` vs `sparse_weight` for corpus type; `fusion_top_k` trades recall against reranker cost; `rerank_top_k` trades precision against generation context window.
