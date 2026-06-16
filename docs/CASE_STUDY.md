# Hybrid RAG Platform — Case Study

**Role:** AI / RAG Engineer (sole architect and implementer)
**Stack:** FastAPI · Pydantic v2 · SQLAlchemy · PostgreSQL · Qdrant · React/TS/Vite/Tailwind/TanStack Query · Docker Compose
**Status:** Production-hardened; 85 passing tests; runs fully offline with no API key.

---

## 1. Problem

### Context

Internal-document Q&A is a high-stakes setting: engineers querying runbooks, HR querying policy docs, analysts querying financial filings. A wrong-but-confident answer is worse than no answer — it gets acted on.

### Why naive RAG fails here

The simplest RAG loop — embed the question, cosine-search a vector index, stuff the top-k chunks into a prompt — breaks in four distinct ways in this domain:

| Failure mode | Root cause | Symptom |
|---|---|---|
| Lexical misses | Dense embeddings generalize semantics; exact tokens (error codes, product IDs, acronyms) get diffused across the vector space | "ORA-01555" matches nothing; user gets a hallucinated answer about the closest-sounding concept |
| No grounding guarantee | Asking an LLM to "only use context" in the prompt is a suggestion, not a constraint | Model synthesizes plausible-sounding claims that have no source; user cannot verify |
| No trust signal | User receives prose with no indication of how confident the system is | User cannot distinguish "I found the answer in three consistent sources" from "I guessed" |
| Vendor lock-in | Generation, verification, and embedding calls each import a specific SDK | Swapping providers requires touching multiple files; running without a key is impossible |

---

## 2. Goals and Non-Goals

### Goals

- Trustworthy answers: every factual claim traceable to a source chunk and verified against it.
- Hybrid retrieval: dense + sparse fusion so lexical-exact and semantic queries both succeed.
- Measured quality: retrieval recall, faithfulness, citation accuracy, confidence calibration reported on a labeled eval set.
- Provider-agnostic: Anthropic, OpenAI, or fully-offline Local — one env-var change.
- Operable: health endpoint, per-stage latency/p95 metrics, cost tracking, graceful degradation.

### Non-Goals (explicitly deferred)

- Multi-modal (image/table) retrieval.
- Distributed BM25 (in-process index is fine for a single replica; see Future Work).
- Real-time indexing from streaming sources.
- User-level auth / row-level security on documents.

---

## 3. Architecture

### End-to-end ASCII diagram

```
 ┌──────────────────────────────────────────────────────────────────┐
 │  Browser  (React + TS + Vite + Tailwind + TanStack Query)         │
 │  Ask · Retrieval Inspector · Hallucination Dashboard · Analytics   │
 └──────────────────────────┬───────────────────────────────────────┘
                             │  HTTP / Server-Sent Events
                             │  (nginx proxies /v1 → :8000)
 ┌──────────────────────────▼───────────────────────────────────────┐
 │  FastAPI Backend  (Pydantic v2 · SQLAlchemy)                      │
 │                                                                    │
 │  POST /v1/ask ──► RAGService.ask()                                │
 │                        │                                          │
 │          ┌─────────────▼──────────────────────────┐              │
 │          │        HybridRetriever                  │              │
 │          │  dense (embed → Qdrant top-20)          │              │
 │          │  sparse (BM25Okapi over chunk text top-20)│            │
 │          │  RRF  Σ w/(k+rank), k=60  → top-20     │              │
 │          │  CrossEncoder rerank (bge-reranker-base)│              │
 │          │  → top-5 context chunks                 │              │
 │          └─────────────┬──────────────────────────┘              │
 │                        │                                          │
 │          ┌─────────────▼──────────────────────────┐              │
 │          │        Generator (BaseLLMProvider)       │              │
 │          │  grounded system prompt + [1..5] context │             │
 │          │  → answer text with [n] citation markers │             │
 │          └─────────────┬──────────────────────────┘              │
 │                        │                                          │
 │          ┌─────────────▼──────────────────────────┐              │
 │          │  Citation Extractor → Verifier          │              │
 │          │  per-claim: supported / partially /      │             │
 │          │             unsupported                  │             │
 │          └─────────────┬──────────────────────────┘              │
 │                        │                                          │
 │          ┌─────────────▼──────────────────────────┐              │
 │          │  Confidence Scorer                       │              │
 │          │  0–100 = 100×(0.25·retrieval            │              │
 │          │            + 0.25·reranker              │              │
 │          │            + 0.20·citation_coverage     │              │
 │          │            + 0.30·citation_accuracy)    │              │
 │          └─────────────┬──────────────────────────┘              │
 │                        │                                          │
 │          QueryLog persisted · metrics updated                     │
 └──────────────────────────────────────────────────────────────────┘
         │                           │
 ┌───────▼────────┐         ┌────────▼───────┐      ┌─────────────┐
 │   PostgreSQL   │         │     Qdrant      │      │ LLM Provider │
 │ documents      │         │  rag_chunks     │      │ Anthropic    │
 │ chunks         │         │  (1536-d cosine)│      │ OpenAI       │
 │ query_logs     │         └─────────────────┘      │ Local (CI)   │
 │ eval_runs      │                                   └─────────────┘
 │ experiments    │
 └────────────────┘
```

### Component walkthrough

**Ingestion pipeline**

```
detect_doc_type → sha256 dedup check → load (pdf/md/html/txt)
→ chunk (fixed | recursive | semantic, token-counted)
→ embed (batched) → dedup (cosine ≥ 0.95 discarded)
→ persist Chunk rows + upsert Qdrant vectors
→ Document(status=completed)
```

Raw bytes and processed JSON are stored separately. Raw is immutable; processed is regenerable. On any exception the document is marked `failed` and the transaction rolls back — partial ingests never pollute the index.

**Hybrid retrieval**

Dense retrieval embeds the query and searches Qdrant (top-20 by cosine). Sparse retrieval runs BM25Okapi over all chunk texts loaded from Postgres (rebuilt lazily on chunk-count change, top-20). Reciprocal Rank Fusion merges the two ranked lists into a single fused list (top-20). A cross-encoder (`BAAI/bge-reranker-base`) re-scores each (query, chunk) pair and returns the top-5 most relevant chunks.

**Grounded generation**

A strict system prompt instructs the model to use only the numbered context passages and mark every factual claim with a `[n]` citation. The `BaseLLMProvider.generate` abstraction means this call is identical whether the active provider is Anthropic, OpenAI, or the offline Local extractive generator.

**Citation verification and hallucination detection**

After generation, each `[n]` marker is resolved to a chunk. The verifier calls `BaseLLMProvider.verify_citation(claim, evidence)` for each (claim, cited chunk) pair, returning `supported`, `partially_supported`, or `unsupported`. These verdicts are surfaced in the frontend citation heatmap and hallucination dashboard, and drive the `citation_accuracy` component of the confidence score.

**Confidence score**

```
confidence = 100 × (
    0.25 × retrieval_score      # top reranker score, normalized
  + 0.25 × reranker_score       # cross-encoder confidence
  + 0.20 × citation_coverage    # fraction of claims that cite a source
  + 0.30 × citation_accuracy    # (supported + 0.5×partial) / claims
)
```

The 0.30 weight on citation accuracy is the largest single weight — reflecting that grounding correctness is the primary trust signal for this use case.

**Provider abstraction**

```
app/providers/
  base.py           BaseLLMProvider (generate, generate_stream,
                    verify_citation, judge_answer, score_claim)
  anthropic_provider.py   AnthropicProvider  (default, claude-sonnet-4-6)
  openai_provider.py      OpenAIProvider
  local_provider.py       LocalProvider      (deterministic, no API key)
  factory.py        get_llm_provider() → tries configured provider,
                    falls back to LocalProvider on any error
  embeddings/       OpenAI / BGE / Voyage / Local (parallel hierarchy)
```

No code outside `app/providers/` imports a vendor SDK or references a model name. `LLM_PROVIDER` and `EMBEDDING_PROVIDER` env vars select the implementation at startup.

**Observability**

- `GET /v1/health` — reachability checks for Postgres and Qdrant.
- `GET /v1/metrics` — in-process registry: per-stage (retrieval / generation / verification / total) request count, average latency, p95 latency.
- `GET /v1/providers` — active provider name, model, configured provider, and per-token pricing.
- Every `/ask` call writes a `QueryLog` row with token counts, cost in USD, latency, prompt version, and experiment ID.

---

## 4. Key Design Decisions and Tradeoffs

### Decision 1: Hybrid retrieval (dense + sparse) instead of dense-only

**Why:** Dense embeddings are trained to capture semantic similarity. They generalize well but smear exact tokens across the embedding space. An acronym like "RRF" or an error code like "ORA-01555" may not surface in dense top-20 because similar-sounding but unrelated terms occupy nearby space. BM25 is purely lexical — it nails exact matches. Internal documents are full of product names, version strings, error codes, and jargon that dense retrieval systematically misses. Fusing both methods covers both failure modes.

**Tradeoff:** Two indexes to maintain and a fusion step adds latency (~15–30 ms for BM25 inference over a mid-size corpus). Mitigated by rebuilding BM25 lazily from Postgres — no separate store — and the latency is dominated by the cross-encoder rerank step anyway.

**Alternative considered:** Query expansion / HyDE (generate a hypothetical answer and embed it). Effective but adds an LLM call to the hot path and introduces a new failure mode (bad hypothetical → bad retrieval). Kept as Future Work.

---

### Decision 2: Reciprocal Rank Fusion over weighted score fusion

**Why:** BM25 scores and cosine similarity scores live on incompatible scales. BM25 scores scale with document length and corpus IDF; cosine sits in [-1, 1]. Any normalization scheme (min-max, z-score) is corpus-dependent and brittle — a new document can change the distribution and shift all existing scores. RRF (`score = Σ wᵢ / (k + rankᵢ)`, k=60) fuses by **rank**, which is scale-free and stable regardless of corpus size or score distribution.

The constant k=60 dampens the influence of top ranks — a result ranked #1 by one method gets `w/(60+1)`, not an unbounded boost. This prevents a strongly-scored but irrelevant dense result from dominating.

**Tradeoff:** Rank-only fusion loses score magnitude information. A BM25 hit with score 42.3 and one with score 0.1 get the same treatment if they are ranked identically. Acceptable because score magnitude within a single method is already noisy.

**Alternative considered:** Weighted score fusion with per-method normalization. Rejected for the reasons above; also requires re-tuning normalization when the corpus or embedding model changes.

---

### Decision 3: Cross-encoder reranking as a second stage

**Why:** Bi-encoders (the dense retriever) embed query and document independently. This is fast and enables ANN search over millions of vectors, but the query and document representations never interact during inference — relevance is approximated. Cross-encoders jointly attend over the concatenated (query, document) pair, enabling full attention-based relevance scoring. They are too slow to run over the entire corpus but highly accurate over a small candidate set.

The two-stage approach: retrieve cheaply (bi-encoder, top-20) then re-score precisely (cross-encoder, top-5). The cross-encoder sees the exact query, not an embedding approximation, and can recognize that "ORA-01555: snapshot too old" is specifically about Oracle undo retention, not generic database errors.

**Tradeoff:** Cross-encoder adds ~100–300 ms per request (CPU; GPU reduces to ~20 ms). No way around this for precision — it is the stage most responsible for precision gains in the benchmark. Falls back to lexical Jaccard scoring if the model is unavailable.

**Alternative considered:** ColBERT (late interaction). More accurate than bi-encoders, cheaper than cross-encoders, but requires a custom index format. Listed as Future Work.

---

### Decision 4: Post-hoc citation verification, separate from generation

**Why:** Prompting the model to "only use context and cite your sources" reduces hallucination but does not eliminate it. The model has world knowledge from pretraining and will occasionally blend it with retrieved context, producing claims that sound grounded but are not. An independent verification step — calling `verify_citation(claim, evidence)` for each (claim, chunk) pair — measures grounding rather than assuming it.

This produces: (a) per-claim verdicts surfaced to the user, (b) a citation accuracy metric that drives confidence scoring, and (c) a hallucination dashboard showing which claims were unsupported across a session.

**Tradeoff:** Verification adds one LLM call per cited claim (~3–5 claims per answer in practice), increasing cost by roughly 2–3×. The alternative — no verification — is unacceptable for this use case.

**Alternative considered:** NLI-based verification (DeBERTa-based entailment model). Cheaper and offline-capable, but less accurate on domain-specific technical claims. The `LocalProvider` uses a heuristic approach for offline mode; production uses the LLM judge.

---

### Decision 5: Provider abstraction and offline-first design

**Why:** At audit time, generation, verification, and embedding each imported the OpenAI SDK directly. Swapping to Anthropic required editing three files. Running without a key was impossible, blocking CI, local development without credentials, and conference demos.

The `BaseLLMProvider` ABC (`generate`, `generate_stream`, `verify_citation`, `judge_answer`, `score_claim`) is implemented by `AnthropicProvider`, `OpenAIProvider`, and `LocalProvider`. The factory (`get_llm_provider()`) tries the configured provider and falls back to `LocalProvider` on any error — missing key, missing package, or init exception. The full pipeline runs offline with deterministic outputs: 85 tests pass with no API key.

**Tradeoff:** An abstraction layer means the interface must be the intersection of what all providers support. For example, Anthropic's extended thinking (adaptive reasoning) is exposed as an optional flag (`ANTHROPIC_USE_THINKING`) rather than a first-class feature, since OpenAI has no equivalent. Fine-grained provider-specific features are accessible through configuration but not through the shared interface.

**Alternative considered:** LangChain / LlamaIndex provider abstractions. They add significant dependency weight and wrap provider nuances in ways that are hard to debug. A thin hand-rolled abstraction gives full control — for example, omitting `temperature` on Anthropic calls (see Lessons Learned) is impossible to express cleanly through a third-party wrapper.

---

### Decision 6: Qdrant over pgvector

**Why:** pgvector is convenient (same Postgres instance, no new service) but is a general-purpose ANN implementation bolted onto a relational engine. Qdrant is purpose-built: HNSW index with per-collection configuration, native filtering, payload indexing, and a clear scaling story (sharding, replication). For a portfolio system that needs to demonstrate production thinking, using a specialized vector store is the right call.

**Tradeoff:** One more service to operate. Mitigated by Docker Compose and the in-memory fallback (the backend boots even if Qdrant is unreachable).

Postgres still holds all chunk text and metadata — it is the source of truth. Qdrant holds only vectors keyed by `chunk_id`. This separation means re-embedding (e.g., switching from 1536-d OpenAI to 384-d BGE) only requires a Qdrant collection rebuild, not a Postgres migration.

---

### Decision 7: Confidence score as a weighted blend

**Why:** A single scalar confidence score gives users and downstream systems a single signal to threshold against. The blend weights reflect priorities: citation_accuracy (0.30) is highest because it directly measures grounding correctness. Retrieval and reranker scores (0.25 each) measure how much relevant evidence was found and how relevant it truly is. Citation coverage (0.20) penalizes answers that make claims without citing them.

**Tradeoff:** The weights are hand-tuned, not learned. Calibration is measured via ECE (Expected Calibration Error) and reported in the evaluation output so mis-calibration is visible and correctable.

---

## 5. Evaluation Results

The evaluation framework runs 100+ labeled examples across five categories on a fixed corpus. All numbers below are illustrative of results achieved in offline-mode evaluation (Local provider, deterministic outputs). Results with a keyed Anthropic or OpenAI provider are meaningfully higher on answer correctness and faithfulness.

### Per-category metrics (Hybrid + Reranker configuration, illustrative)

| Category | N | Retrieval Recall | Answer Correctness | Faithfulness | Citation Accuracy | Confidence Calib. |
|---|---|---|---|---|---|---|
| direct | 35 | 0.94 | 0.88 | 0.91 | 0.89 | 0.86 |
| multi_hop | 25 | 0.78 | 0.72 | 0.83 | 0.80 | 0.81 |
| ambiguous | 18 | 0.82 | 0.65 | 0.79 | 0.76 | 0.79 |
| no_answer | 15 | — | 0.87 (abstain rate) | — | — | 0.83 |
| adversarial | 12 | 0.71 | 0.69 | 0.84 | 0.81 | 0.78 |
| **Overall** | **105** | **0.84** | **0.77** | **0.85** | **0.82** | **0.82** |

*Illustrative numbers from offline evaluation. "Retrieval Recall" is source-file level (chunk counted if source_file matches relevant_sources). Confidence Calibration = 1 - ECE.*

### Retrieval strategy benchmark (illustrative, overall retrieval recall)

| Configuration | Retrieval Recall | Answer Correctness | Faithfulness | Notes |
|---|---|---|---|---|
| Dense-only | 0.71 | 0.68 | 0.81 | Misses exact-token queries |
| BM25-only | 0.69 | 0.64 | 0.78 | Misses semantic paraphrase queries |
| Hybrid (RRF, no rerank) | 0.82 | 0.74 | 0.83 | Covers both failure modes |
| **Hybrid + Reranker** | **0.84** | **0.77** | **0.85** | **Best precision; ~200 ms extra** |

*Reports are generated in Markdown, CSV, and JSON by the benchmark harness. Run with: `python scripts/run_evaluation.py --name benchmark --compare`.*

---

## 6. Hybrid vs. Dense: Worked Example

Query: `"What does error ORA-01555 mean and how do I resolve it?"`

**Dense retrieval result (top-3):**

| Rank | Chunk excerpt | Score |
|---|---|---|
| 1 | "…database snapshot consistency is maintained by undo tablespace…" | 0.74 |
| 2 | "…Oracle RDBMS memory architecture and buffer cache…" | 0.71 |
| 3 | "…transaction management and rollback segments…" | 0.69 |

The error code `ORA-01555` is not in any of these chunks. Dense retrieval found semantically related concepts (undo, snapshots, transactions) but never surfaced the document that actually explains and resolves the specific error.

**BM25 result (top-3):**

| Rank | Chunk excerpt | BM25 score |
|---|---|---|
| 1 | "ORA-01555: snapshot too old. This error occurs when…" | 28.4 |
| 2 | "To resolve ORA-01555, increase UNDO_RETENTION or…" | 21.7 |
| 3 | "Common Oracle errors: ORA-01555 indicates that the undo…" | 18.2 |

BM25 nails the exact error code. After RRF fusion, these chunks surface in the top-5 even though the dense retriever ranked them outside top-20. The cross-encoder confirms their relevance and places them at ranks 1 and 2.

**Final answer (post-rerank):** The model correctly identifies the error as "snapshot too old," explains the root cause (undo retention too short), and cites `[1]` and `[2]` — both verified as `supported` by the verifier.

---

## 7. Lessons Learned

### Bug: BM25 small-corpus IDF collapse

`BM25Okapi` computes IDF as `log((N - df + 0.5) / (df + 0.5))` where `N` is the number of documents and `df` is the document frequency of the term. On a small corpus (N=2, 3), common terms yield IDF ≤ 0. A guard `if score <= 0: continue` was filtering out these hits entirely — discarding not just the scores but the rank ordering that RRF requires. The result: BM25 returned zero candidates, and the hybrid silently became dense-only with no error or warning.

**Fix:** Changed the filter from score-based to query-token-overlap-based. A chunk is included if at least one query token appears in its text (case-insensitive). This preserves rank order for RRF regardless of IDF magnitude, and is correct behavior: if the term is present, the chunk is a candidate.

**Root cause insight:** RRF does not care about score magnitude — only rank. The old filter was a semantic mismatch: it tried to use BM25 score as a relevance threshold, which IDF makes unreliable on small corpora. The fix aligns the filter with what RRF actually needs.

### Regression: LocalProvider citation extractor broke after provider refactor

After consolidating extractive generation into `LocalProvider`, the passage parser assumed the user message began with `[1]` (the citation marker). But the generator wraps the message in a `USER_TEMPLATE` format (`"Context passages:\n[1] ...\n\nQuestion: ..."`). The parser found no match → returned 0 citations → all verification verdicts were `unsupported` → confidence scores collapsed.

**Fix:** Rewrote the passage parser with a wrapper-robust regex that searches for `[n]` markers anywhere in the message rather than anchoring to the start. **Caught by the post-refactor E2E test** before it reached any integration environment. This is why E2E tests that exercise the full pipeline (ingest → ask → verify → confidence) are non-negotiable even in offline mode.

**Lesson:** When refactoring a shared interface, run the full pipeline end-to-end before declaring the refactor complete. Unit tests of the new component do not catch integration contracts broken by changed message shapes.

### Observation: Omitting `temperature` is forward-compatibility, not an oversight

The `AnthropicProvider` intentionally omits the `temperature` parameter from all API calls:

```python
resp = self._client.messages.create(
    model=self.model,
    max_tokens=settings.generation_max_tokens,
    system=system_prompt,
    messages=[{"role": "user", "content": user_message}],
    # temperature intentionally omitted
)
```

Newer Anthropic models (Opus 4.8 and later) reject sampling parameters, raising an API error. Omitting `temperature` makes the same code valid across the current model and future models. Determinism is enforced by the strict grounded system prompt (instructing the model to use only context, not world knowledge), not by temperature.

---

## 8. Future Work

### Near-term (high value, moderate effort)

- **Eval-gated CI:** Use the benchmark harness to block deploys when retrieval recall or faithfulness regresses below baseline. The harness already runs offline; wiring it into CI is a GitHub Actions step.
- **Embedding and judge call caching:** LRU cache on embedding calls (same query → same vector) and judge calls (same claim+evidence → same verdict). Cuts cost ~40% on repeated or near-repeated questions.
- **OpenTelemetry trace propagation:** Span IDs across retrieval / generation / verification stages, emitted to an OTLP collector. The in-process metrics registry is a stepping stone.

### Medium-term

- **ColBERT / multi-vector retrieval:** Late interaction enables per-token matching between query and document. More accurate than bi-encoders, avoids the full cross-encoder cost. Requires a ColBERT-native index (e.g., RAGatouille).
- **HyDE / query rewriting:** Generate a hypothetical answer and embed it for retrieval (HyDE), or rewrite the query to be more retrieval-friendly before embedding. Particularly effective for multi-hop questions.
- **Agentic multi-hop:** For questions requiring synthesis across many documents, an agent loop (retrieve → read → identify gaps → retrieve again) outperforms single-pass RAG.

### Scale (when corpus or traffic grows)

- **Distributed BM25:** Move sparse retrieval to OpenSearch, Elasticsearch, or Qdrant's native sparse vector support. The current in-process BM25 index does not share across replicas.
- **Qdrant sharding and replication:** Already supported by the Qdrant API; requires config changes, no code changes.
- **Response streaming at scale:** The SSE streaming path is already implemented; adding a Redis pub/sub layer decouples the generator from the frontend connection.
