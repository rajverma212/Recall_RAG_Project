# Future Work

## Overview

This document describes a credible roadmap for evolving the platform from a production-grade single-tenant RAG system into an enterprise-scale, observable, and continuously evaluated retrieval platform. Items are grouped into near-term (1–3 months), mid-term (3–9 months), and long-term (9+ months) horizons based on implementation complexity and expected impact. Each item includes a rationale grounded in the current system's known limitations.

---

## Near-Term (1–3 months)

### 1. Embedding and Response Caching

**Current state:** Every query triggers an OpenAI embedding API call (~100 ms, ~0.00002 USD) and a generation call (~$0.0003 per query). Repeated or near-identical queries pay the full cost on every call.

**Proposed:** A two-layer cache:
- **Exact cache:** Redis/Postgres key-value store with `sha256(question)` → cached `AskResponse`. Zero-latency repeat queries.
- **Semantic cache:** Embed the query and check cosine similarity against cached query embeddings. If similarity ≥ threshold (e.g., 0.97), serve the cached response. This catches paraphrases ("What languages does he know?" vs "Which programming languages is he proficient in?").

**Trade-offs:** Semantic cache adds one embedding call overhead per query (but skips the generation call, a net saving). Cache invalidation must be triggered when new documents are ingested, since the correct answer may change.

**Impact:** 40–70% cost reduction on conversational workloads with repetitive questions.

---

### 2. Eval-Driven CI Gates

**Current state:** Evaluation is a manual step (`scripts/run_evaluation.py`). There is no automated check preventing a retrieval regression from reaching production.

**Proposed:** Integrate the evaluation runner into the CI pipeline (GitHub Actions / GitLab CI):

```
On PR merge to main:
  1. Build Docker image
  2. docker compose up (with test corpus)
  3. run_evaluation.py --name ci_run --strategy recursive
  4. Assert: retrieval_recall ≥ 0.85
             answer_correctness ≥ 0.78
             faithfulness ≥ 0.75
  5. Block merge if any metric regresses > 5% from baseline
```

Store the baseline metrics in `evaluation/baselines/baseline.json` (committed to the repo). The CI script compares against this file. A regression in no-answer correctness is treated as a critical failure and always blocks the merge.

**Impact:** Prevents silent regressions when changing chunking parameters, prompt versions, or retrieval logic. Establishes a reproducible quality bar for every release.

---

### 3. OpenTelemetry Traces and Prometheus Metrics

**Current state:** Per-query `trace` data is available via the `/ask` API but is not exported to any observability backend. There are no infrastructure metrics (CPU, memory, request rate, error rate).

**Proposed:**
- Instrument FastAPI with `opentelemetry-instrumentation-fastapi`. Export traces to Jaeger or Tempo (OTLP exporter). Each retrieval stage (dense, BM25, RRF, rerank, generate) becomes a named span with duration and result count attributes.
- Expose a `/metrics` endpoint (Prometheus format) via `prometheus-fastapi-instrumentator`. Key counters: `rag_queries_total`, `rag_confidence_score_histogram`, `rag_retrieval_latency_seconds` (by stage), `rag_cost_usd_total`.
- Deploy Grafana + Prometheus as additional Compose services (dev) or as a sidecar (production).

**Impact:** Enables p50/p95/p99 latency dashboards, alerting on error rate spikes, and capacity planning based on actual usage patterns.

---

### 4. Query Rewriting and HyDE

**Current state:** The raw user query is embedded as-is. Short or ambiguous queries ("his latest role?") produce embeddings that may not match the longer, more detailed chunk text well.

**Two complementary techniques:**

**Query rewriting:** Use an LLM to expand the query before embedding.
```
User: "his latest role?"
Rewritten: "What is the most recent job title, company, and responsibilities of the candidate?"
```
The rewritten query produces a richer embedding that aligns better with chunk vocabulary.

**HyDE (Hypothetical Document Embeddings, Gao et al. 2022):** Generate a hypothetical answer to the query using the LLM, then embed that answer instead of (or alongside) the query. Since the hypothetical answer is in the same register as the document chunks, its embedding is closer to relevant chunks in vector space.

**Trade-offs:** Both techniques add one LLM call to the hot path (+200–500 ms, ~$0.0001). HyDE can be cached per query. The gain is largest on short, keyword-sparse queries and ambiguous queries — exactly the categories where the current system underperforms.

---

## Mid-Term (3–9 months)

### 5. ColBERT / Multi-Vector Late Interaction

**Current state:** Dense retrieval uses a single 1536-d vector per chunk (bi-encoder). This compresses the entire chunk into one point in space, losing intra-chunk token-level structure.

**Proposed:** Replace or augment the bi-encoder with **ColBERT** (Khattab & Zaharia 2020). ColBERT stores one vector per token (not one per chunk). At query time, it computes a MaxSim score:

```
ColBERT_score(q, d) = Σ_{i∈q_tokens} max_{j∈d_tokens} (q_i · d_j)
```

This late-interaction pattern gives near-cross-encoder precision at near-bi-encoder latency. Qdrant v1.10+ supports multi-vector payloads, making ColBERT-style retrieval feasible within the existing infrastructure.

**Trade-offs:** ColBERT requires significantly more storage (~128 vectors per chunk vs 1) and a different ANN strategy (PLAID index). The indexing pipeline is more complex. For a resume corpus of <10k chunks, the storage overhead is manageable; for millions of chunks, it requires careful sharding.

**Impact:** Strongest quality gain available without changing the retrieval architecture fundamentally. Studies report 5–15% nDCG improvement over standard bi-encoder + reranker pipelines.

---

### 6. Fine-Tuned Domain Reranker

**Current state:** `BAAI/bge-reranker-base` is trained on general web data (MS MARCO). Its notion of relevance is calibrated for web search, not for resume/career document Q&A.

**Proposed:** Collect positive/negative pairs from production queries:
- Positive: (query, chunk) pairs where `citation_accuracy ≥ 0.9` and `status = supported`
- Negative: (query, chunk) pairs where the chunk appeared in the top-20 fused results but was not cited or was marked `unsupported`

Fine-tune `bge-reranker-base` on these pairs using contrastive loss (InfoNCE). The resulting domain-adapted reranker should produce significantly better nDCG@5 on the evaluation set.

**Trade-offs:** Requires accumulating ~1,000–5,000 labelled pairs before fine-tuning is worthwhile. Fine-tuned models must be re-evaluated whenever the corpus domain shifts significantly. Adds a model management concern (versioning, rollback).

**Impact:** Expected 3–8% nDCG@5 improvement on in-domain queries with minimal latency change (same model architecture and size).

---

### 7. Agentic / Iterative Multi-Hop Retrieval

**Current state:** Retrieval is a single-pass operation: one query → one retrieval round → one generation. Multi-hop questions ("Who was her manager at Acme Corp, and what did that manager say about her?") require synthesising information that may not be co-located in any single chunk.

**Proposed:** An iterative retrieval loop:

```
Query
  │
  ▼
Retrieval round 1 → partial answer + identified gaps
  │
  ▼
Generate sub-questions from gaps
  │
  ▼
Retrieval round 2 (per sub-question) → additional context
  │
  ▼
Final generation with all collected context
```

This pattern (ReAct, RAG-Token, Iterative RAG) handles multi-hop questions that the current single-pass pipeline misses. The evaluation dataset's `multi_hop` category (17 examples) provides a ready-made benchmark for measuring improvement.

**Trade-offs:** Latency multiplies with rounds (2–3 rounds → 2–3× end-to-end time). Cost scales similarly. A maximum-rounds limit and a convergence check ("did round N retrieve any new chunks?") are essential safeguards against infinite loops.

---

### 8. Multi-Tenancy and Per-Tenant Indexes

**Current state:** All documents share a single Qdrant collection and PostgreSQL schema. All queries search the full corpus.

**Proposed:** Namespace isolation:
- **Qdrant:** Use collection-per-tenant or payload-filtered search with a `tenant_id` field. Collection-per-tenant is simpler and provides stronger isolation; payload filtering is more resource-efficient at lower tenant counts.
- **PostgreSQL:** Row-Level Security (RLS) on the `documents` and `chunks` tables, with a `tenant_id` column and a policy enforcing that sessions only see their own rows.
- **API:** JWT authentication carrying `tenant_id`; the application layer injects the tenant filter into every retrieval call.

**Trade-offs:** Collection-per-tenant is simple but does not scale beyond ~1,000 tenants (Qdrant has per-collection overhead). Payload filtering scales to millions of tenants but requires careful index design. RLS adds a small PostgreSQL overhead (~5 ms per query).

---

### 9. Guardrails and PII Redaction

**Current state:** Uploaded documents and generated answers are stored and returned without scanning for personally identifiable information (PII). In HR/legal contexts, this is a compliance risk.

**Proposed:**
- **Ingest-time PII detection:** Use `presidio-analyzer` (Microsoft) or `spacy` NER to detect names, SSNs, phone numbers, email addresses, and financial data in uploaded documents. Flag or redact before storing in the vector index.
- **Generation-time guardrails:** Use `guardrails-ai` or a custom prompt prefix to prevent the generation model from reproducing raw PII from context chunks. Instead, refer to entities by role ("the candidate", "the employer").
- **Query guardrails:** Detect and reject queries that are attempting PII extraction attacks ("list all phone numbers in the documents").

---

## Long-Term (9+ months)

### 10. GraphRAG

**Current state:** Retrieval treats chunks as independent units. Relationships between entities across chunks (person → company → role → project → skill) are not explicitly modelled.

**Proposed (Microsoft GraphRAG pattern):** During ingestion, extract entities and relationships using an LLM and build a knowledge graph (Neo4j or a Postgres graph extension). At query time, combine vector retrieval with graph traversal: start from the vector-retrieved chunks, expand to related entities in the graph, and include the expanded context in generation.

**When it matters most:** Multi-hop questions where the answer requires traversing entity relationships. The current `multi_hop` eval category is the direct benchmark. GraphRAG is most valuable when the corpus contains many interconnected entities (e.g., multiple resumes, organisational documents, project histories).

**Trade-offs:** Significantly more complex ingestion pipeline. Entity extraction quality depends on the LLM. Graph maintenance (incremental updates) is non-trivial. For corpora of <100 documents, the overhead is rarely justified.

---

### 11. Incremental Re-Indexing

**Current state:** Re-ingesting a modified document requires deleting and re-uploading it. There is no mechanism for detecting which chunks changed and updating only those.

**Proposed:** Content-addressable chunk storage using SHA-256 hashes. On re-ingest, compare chunk hashes against the stored index. Only changed chunks trigger embedding + upsert; unchanged chunks are skipped. This reduces re-ingestion cost from O(document size) to O(changed content size).

**Dependency:** Requires deterministic chunking (same text always produces the same chunk boundaries). Fixed and recursive chunking strategies are deterministic; semantic chunking (percentile-based) is not and requires a stability improvement before incremental re-indexing is feasible.

---

### 12. Semantic Cache with Vector Similarity

**Enhancement to Item 1 (near-term exact cache):** Rather than a fixed cosine threshold for cache hits, use a learned threshold per query category. `direct` queries benefit from a high threshold (0.97) because small wording changes can change the expected answer. `ambiguous` queries should have a lower threshold (0.90) to avoid serving stale cached answers to meaningfully different questions. The threshold can be learned from the evaluation dataset's category labels.

---

## Summary Table

| Item | Term | Expected Impact | Implementation Complexity |
|---|---|---|---|
| Embedding + response cache | Near | High (cost, latency) | Low |
| Eval-driven CI gates | Near | High (quality assurance) | Low |
| OpenTelemetry + Prometheus | Near | Medium (observability) | Medium |
| Query rewriting + HyDE | Near | Medium (recall on ambiguous) | Low |
| ColBERT multi-vector | Mid | High (precision) | High |
| Fine-tuned reranker | Mid | Medium (domain precision) | Medium |
| Agentic multi-hop | Mid | High (multi_hop category) | High |
| Multi-tenancy | Mid | High (enterprise readiness) | High |
| Guardrails + PII | Mid | High (compliance) | Medium |
| GraphRAG | Long | High (entity reasoning) | Very High |
| Incremental re-indexing | Long | Medium (ops efficiency) | Medium |
| Learned semantic cache | Long | Low–Medium | Medium |

---

## Interview Talking Points

- **Prioritisation logic:** Near-term items are high-impact with low implementation risk. CI gates and caching are table stakes for any production ML system. Mid-term items require either significant training data (reranker fine-tuning), architectural changes (ColBERT, multi-hop), or cross-cutting concerns (multi-tenancy). Long-term items are high-value but require the corpus and traffic scale to justify the engineering investment.
- **Why ColBERT before fine-tuning?** ColBERT is a generic architecture improvement that does not require labelled data. Fine-tuning requires accumulating production query logs and manual verification of relevance labels. ColBERT can be deployed before production data exists; fine-tuning cannot.
- **CI gates as a quality flywheel:** Without eval-driven CI, every "improvement" to the retrieval pipeline is an act of faith. CI gates turn the evaluation dataset into a continuous regression test, enabling confident iteration. The evaluation framework was designed from the start to support this pattern.
- **HyDE trade-off clarity:** HyDE trades latency and cost (one extra LLM call per query) for improved recall, especially on short queries. The net cost is typically negative (the extra call costs ~$0.0001 but may avoid a failed retrieval that leads to a $0.0003 generation producing a low-confidence answer that the user re-asks). At scale, the economics clearly favour HyDE for short-query workloads.
- **GraphRAG is not always better:** Microsoft's GraphRAG paper showed large improvements on community-summarisation tasks but smaller improvements (and higher costs) on factual Q&A. For resume-centric RAG, the entity graph adds clear value only when the corpus spans multiple interconnected people and organisations. For single-document use cases, the current chunk-based approach is more cost-effective.
