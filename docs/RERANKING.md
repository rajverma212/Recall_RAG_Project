# Reranking

## Overview

After Reciprocal Rank Fusion produces a fused shortlist of 20 candidates, a cross-encoder reranker re-scores each candidate against the original query and selects the top 5 for generation. Reranking is the highest-precision stage of the pipeline: it has full access to both the query and the chunk text simultaneously, which is exactly what bi-encoders lack.

---

## Bi-Encoder vs Cross-Encoder

The distinction is architectural and determines the fundamental precision/latency trade-off.

### Bi-Encoder (used in DenseRetriever)

```
  Query ─────► Encoder ────► q_vec (1536-d)
                                              ──► cosine_sim(q_vec, d_vec) = scalar
  Doc   ─────► Encoder ────► d_vec (1536-d)
```

The query and document are encoded **independently**. Their interaction is reduced to a dot product over fixed-size vectors. This enables pre-computation of document vectors at index time and ANN lookup at query time — O(log N) per query regardless of corpus size. The trade-off is that cross-token interactions (e.g., recognising that "Apple" in the query refers to the company while a chunk discusses the fruit) are lost once both sequences are independently compressed into fixed vectors.

### Cross-Encoder (used in Reranker)

```
  [CLS] query [SEP] chunk text [SEP]
         │
     Transformer
         │
     Linear head
         │
    relevance score
```

The query and document are concatenated and processed together by the full transformer. Every attention head can attend from any query token to any document token, enabling exact phrase matching, coreference resolution, and fine-grained relevance judgements that bi-encoders miss. The trade-off: cross-encoders cannot pre-compute document representations, so they must run inference per (query, document) pair at query time. Cost is O(N × L²) in sequence length — acceptable only on a small candidate set.

### Comparison table

| Property | Bi-Encoder | Cross-Encoder |
|---|---|---|
| Interaction modelling | Vector similarity only | Full cross-attention |
| Latency per query | O(log N) ANN lookup | O(candidates × seq_len²) |
| Candidate set size | All documents (millions) | Small shortlist (20–100) |
| Precompute doc vecs? | Yes | No |
| Relative precision | Moderate | High |
| Use in this system | Stage 1 (DenseRetriever) | Stage 4 (Reranker) |

---

## Why Rerank After Fusion?

RRF fusion improves recall by combining two retrievers' candidate sets. But RRF scores are based on ranks from each retriever, not on true query-document relevance. A chunk ranked 3rd by both dense and BM25 will outscore one ranked 1st by dense and absent from BM25 — even if the first chunk is factually more relevant to the specific question.

The reranker corrects this: it ignores the upstream ranks entirely and scores each of the 20 fused candidates independently against the query using cross-attention. This two-stage architecture is the standard retrieve-then-rerank pattern used in production RAG systems (e.g., Cohere Rerank, BGE-Reranker, MonoT5) and consistently improves nDCG@5 and MRR over retrieval alone.

---

## Model: BAAI/bge-reranker-base

`BAAI/bge-reranker-base` is a 278M-parameter BERT-based cross-encoder fine-tuned on MS MARCO and a large multilingual corpus by the Beijing Academy of Artificial Intelligence. It outputs a scalar logit that the system sigmoid-normalises to `[0, 1]`.

### Why bge-reranker-base over alternatives?

| Model | Params | BEIR avg nDCG@10 | CPU inference (20 pairs) | Notes |
|---|---|---|---|---|
| BAAI/bge-reranker-base | 278M | ~52 | ~80–200 ms | Good balance, Apache-2.0 |
| BAAI/bge-reranker-large | 560M | ~54 | ~300–600 ms | Higher quality, 2× slower |
| cross-encoder/ms-marco-MiniLM-L-6-v2 | 22M | ~48 | ~20–40 ms | Faster, lower quality |
| Cohere Rerank v3 | API | ~57 | ~200–400 ms + network | Highest quality, external dependency |
| MonoT5-base | 250M | ~52 | ~150–300 ms | Comparable quality, generative |

`bge-reranker-base` hits the practical sweet spot: strong quality without the latency of the large model and without the external API dependency of Cohere.

---

## Fallback Chain

The reranker is loaded lazily as a singleton and attempts three backends in order:

```
1. FlagEmbedding FlagReranker (BAAI/bge-reranker-base)
        │
        ▼ (if import fails or model unavailable)
2. sentence-transformers CrossEncoder (BAAI/bge-reranker-base)
        │
        ▼ (if sentence-transformers unavailable)
3. Lexical Jaccard Reranker (character n-gram overlap, no ML)
```

**Step 1 — FlagEmbedding FlagReranker:** The preferred path. `FlagEmbedding` is the upstream library from BAAI and provides the most accurate inference for their model checkpoints, including batching optimisations.

**Step 2 — sentence-transformers CrossEncoder:** A well-maintained alternative that loads the same checkpoint. Output scores are numerically equivalent. Used when `flagembedding` is not installed.

**Step 3 — Lexical Jaccard fallback:** When neither ML library is available (e.g., a minimal Docker layer without model weights), chunks are scored by Jaccard similarity of character bigrams between query and chunk text. This degrades to a near-BM25 quality level but ensures the system returns ranked results rather than raising an exception.

---

## Score Normalisation

Cross-encoders output raw logits (unbounded reals). The system applies a sigmoid:

```
normalised_score = 1 / (1 + exp(−logit))
```

This maps scores to `[0, 1]` with 0 meaning "completely irrelevant" and 1 meaning "perfectly relevant". The normalised scores feed directly into the confidence calculation:

```
reranker_confidence = mean(sigmoid_scores of top rerank_top_k chunks)
```

Sigmoid normalisation is preferred over min-max normalisation because it is monotone, smooth, and does not require knowing the range of possible logits in advance.

---

## Tuning rerank_top_k

`rerank_top_k` (default 5) controls how many chunks are passed to generation after reranking. This is the most direct quality lever in the system.

| rerank_top_k | Effect |
|---|---|
| 3 | Minimal context; fast generation; risks missing supporting evidence |
| 5 | Default; good precision vs context balance for 1–3 page corpora |
| 10 | More evidence; higher generation cost (more tokens); diminishing returns beyond |
| 20 | Passes all fused candidates directly; skips reranker benefit |

Setting `rerank_top_k > fusion_top_k` is a no-op (the reranker simply passes all candidates through).

---

## Cost and Latency Trade-offs

```
Reranker CPU latency breakdown (bge-reranker-base, 20 pairs, 512-token chunks):

  Model load (first request, cached after) : 2–5 s
  Tokenisation (20 × ~600 tokens)          : ~5 ms
  Transformer forward passes (batched)     : ~80–200 ms
  Sigmoid normalisation                    : < 1 ms
  Total per query (warm)                   : ~85–205 ms
```

The reranker runs on CPU by default (`reranker_device=cpu`). Setting `reranker_device=cuda` drops inference time to approximately 10–30 ms on a GPU (e.g., A10G), which becomes relevant at >50 queries/minute. At lower throughput, CPU is entirely adequate.

The reranker does not make any external API calls, which means it contributes zero marginal API cost. The only variable cost in the full pipeline is the OpenAI embedding call and the generation call.

---

## Interview Talking Points

- **Why not just use the cross-encoder to retrieve directly?** Cross-encoders require a forward pass per (query, document) pair. On a corpus of 10,000 chunks at 100 ms/pair that is 1,000 seconds per query. The two-stage retrieve → rerank pattern solves this: cheap bi-encoder + BM25 reduce the candidate set to 20, then the cross-encoder scores only those 20.
- **Why sigmoid over softmax?** Softmax is a distribution over a fixed set — it forces a competition between candidates. Sigmoid treats each score independently, which is correct when absolute relevance matters (a chunk is relevant or it is not, regardless of what other chunks score).
- **Fallback design:** The three-level fallback (FlagEmbedding → CrossEncoder → Jaccard) ensures that a missing package or model weight file degrades gracefully rather than crashing the request. The quality drop is detectable via the confidence score, giving operators a signal to fix the environment.
- **Why lazy singleton?** The BAAI model checkpoint is ~1.1 GB. Loading it at startup would add 2–5 seconds to cold start. Lazy loading defers this cost until the first reranking request, after which the singleton is warm for all subsequent requests.
- **bge-reranker-large vs base:** The large model's quality improvement (~2 nDCG points) rarely justifies 2× latency for interactive RAG. The base model is the right default; large is worth evaluating if offline batch reranking is needed.
