# API Reference

## Overview

All endpoints are prefixed with `/v1`. The API is served by FastAPI on port 8000. Requests and responses use `application/json` except `/ingest` (multipart) and `/ask/stream` (SSE). Pydantic v2 handles validation; invalid requests return HTTP 422 with field-level error detail.

---

## POST /v1/ask

Submit a question and receive a fully grounded answer with citations, verification, and confidence scores.

### Request

```json
{
  "question": "string (required)",
  "stream": false,
  "include_trace": false,
  "prompt_version": "string | null",
  "experiment_id": "string | null"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `question` | string | required | Natural-language question |
| `stream` | bool | false | If true, use `/ask/stream` instead |
| `include_trace` | bool | false | Include per-stage retrieval trace in response |
| `prompt_version` | string | null | Pin a specific prompt version (see `/prompts`) |
| `experiment_id` | string | null | Associate query with an A/B experiment |

### Response — AskResponse

```json
{
  "query_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "question": "What programming languages does the candidate know?",
  "answer": "The candidate is proficient in Python, TypeScript, and Go [1][2].",
  "citations": [
    {
      "marker": "[1]",
      "chunk_id": "abc123",
      "document_id": "doc456",
      "source_file": "resume_v3.pdf",
      "page_number": 1,
      "section_title": "Skills",
      "quote": "Proficient in Python, TypeScript, and Go",
      "text": "<full chunk text>"
    }
  ],
  "verifications": [
    {
      "claim": "The candidate is proficient in Python, TypeScript, and Go.",
      "cited_markers": ["[1]", "[2]"],
      "status": "supported",
      "rationale": "Source chunk explicitly lists Python, TypeScript, and Go under Skills."
    }
  ],
  "confidence": {
    "retrieval_confidence": 0.82,
    "reranker_confidence": 0.91,
    "citation_coverage": 1.0,
    "citation_accuracy": 0.95,
    "score": 89
  },
  "trace": null,
  "cost_usd": 0.00031,
  "latency_ms": 1243,
  "prompt_version": "v1"
}
```

`trace` is `null` unless `include_trace=true`. When included:

```json
{
  "trace": {
    "dense": {
      "name": "dense",
      "results": [
        {
          "chunk_id": "abc123",
          "document_id": "doc456",
          "text": "...",
          "score": 0.87,
          "source_file": "resume_v3.pdf",
          "page_number": 1,
          "section_title": "Skills",
          "heading_path": "Skills > Programming Languages",
          "rank": 1
        }
      ],
      "elapsed_ms": 11
    },
    "bm25": { "name": "bm25", "results": [...], "elapsed_ms": 5 },
    "rrf":  { "name": "rrf",  "results": [...], "elapsed_ms": 0 },
    "reranked": { "name": "reranked", "results": [...], "elapsed_ms": 94 }
  }
}
```

### Example curl

```bash
curl -X POST http://localhost:8000/v1/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the candidate's most recent role?",
    "include_trace": false
  }'
```

---

## POST /v1/ask/stream

Same request schema as `/ask`. Returns a Server-Sent Events stream.

### SSE event format

Each event is a JSON object on a `data:` line, followed by a blank line.

**Token delta:**
```
data: {"type": "token", "text": "The "}

data: {"type": "token", "text": "candidate "}
```

**Completion (final event):**
```
data: {"type": "done", "data": { <full AskResponse object> }}
```

The `done` event's `data` field contains the complete `AskResponse` including citations, verifications, and confidence, allowing the client to render the full structured response after streaming completes.

### Example curl (SSE)

```bash
curl -X POST http://localhost:8000/v1/ask/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"question": "Summarise the candidate's education."}'
```

---

## POST /v1/ingest

Upload a document for ingestion. The document is chunked, deduplicated, embedded, and indexed in both Qdrant and PostgreSQL.

### Request

`Content-Type: multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | file | PDF, DOCX, or TXT file |
| `strategy` | string (query param) | `fixed` \| `recursive` \| `semantic` (optional, uses config default) |

```bash
curl -X POST "http://localhost:8000/v1/ingest?strategy=recursive" \
  -F "file=@/path/to/resume.pdf"
```

### Response

```json
{
  "document_id": "d7e1a2b3-c4d5-6789-abcd-ef0123456789",
  "filename": "resume.pdf",
  "status": "completed",
  "num_chunks": 47,
  "num_duplicates_skipped": 3,
  "message": "Document ingested successfully with recursive chunking."
}
```

| Field | Description |
|---|---|
| `document_id` | UUID of the ingested document |
| `status` | `completed` or `failed` |
| `num_chunks` | Chunks stored (after deduplication) |
| `num_duplicates_skipped` | Chunks with cosine similarity ≥ 0.95 to existing chunks, skipped |
| `message` | Human-readable status message |

---

## GET /v1/documents

List all ingested documents.

```bash
curl http://localhost:8000/v1/documents
```

### Response — array of DocumentOut

```json
[
  {
    "id": "d7e1a2b3-c4d5-6789-abcd-ef0123456789",
    "filename": "resume.pdf",
    "doc_type": "pdf",
    "title": "Raj Verma — Resume",
    "num_pages": 2,
    "num_chunks": 47,
    "status": "completed",
    "chunking_strategy": "recursive",
    "error": null,
    "ingested_at": "2026-06-14T10:23:45Z",
    "completed_at": "2026-06-14T10:23:52Z"
  }
]
```

---

## DELETE /v1/documents/{id}

Delete a document and all its chunks from PostgreSQL and Qdrant.

```bash
curl -X DELETE http://localhost:8000/v1/documents/d7e1a2b3-c4d5-6789-abcd-ef0123456789
```

### Response

```json
{
  "message": "Document d7e1a2b3-... deleted successfully."
}
```

HTTP 404 if the document ID does not exist.

---

## GET /v1/evaluations

List all evaluation runs.

```bash
curl http://localhost:8000/v1/evaluations
```

### Response — array of EvaluationRunOut

```json
[
  {
    "id": "eval-run-uuid",
    "name": "baseline_run_v1",
    "dataset": "evaluation/datasets/eval_set.json",
    "config": {
      "chunking_strategy": "recursive",
      "chunk_size": 512,
      "dense_top_k": 20,
      "rerank_top_k": 5
    },
    "retrieval_recall": 0.87,
    "answer_correctness": 0.81,
    "faithfulness": 0.79,
    "citation_accuracy": 0.76,
    "confidence_calibration": 0.83,
    "created_at": "2026-06-14T11:00:00Z"
  }
]
```

---

## GET /v1/evaluations/{id}

Get full results for a single evaluation run including per-example details.

```bash
curl http://localhost:8000/v1/evaluations/eval-run-uuid
```

### Response

```json
{
  "run": { <EvaluationRunOut> },
  "results": [
    {
      "example_id": "eval_001",
      "category": "direct",
      "question": "...",
      "answer": "...",
      "answer_correctness": 0.95,
      "faithfulness": 1.0,
      "citation_accuracy": 1.0,
      "retrieval_recall": 1.0,
      "confidence_score": 88
    }
  ]
}
```

---

## GET /v1/analytics

Aggregated usage analytics across all queries.

```bash
curl http://localhost:8000/v1/analytics
```

### Response

```json
{
  "total_queries": 342,
  "avg_confidence": 74.3,
  "avg_citation_accuracy": 0.81,
  "avg_latency_ms": 1842,
  "total_cost_usd": 0.412,
  "queries_by_day": [
    { "date": "2026-06-14", "count": 47 }
  ],
  "confidence_histogram": [
    { "bin": "0-10",  "count": 2 },
    { "bin": "10-20", "count": 5 },
    { "bin": "20-30", "count": 8 },
    { "bin": "90-100","count": 71 }
  ],
  "low_confidence_rate": 0.042
}
```

`low_confidence_rate` = fraction of queries where `confidence.score < min_confidence_to_answer`.

---

## GET /v1/experiments

List A/B experiment configurations.

```bash
curl http://localhost:8000/v1/experiments
```

### Response — array of ExperimentOut

```json
[
  {
    "id": "exp-uuid",
    "name": "sparse_weight_ablation",
    "description": "Compare sparse_weight 0.5 vs 1.0 vs 2.0",
    "config": { "sparse_weight": 2.0 },
    "created_at": "2026-06-13T09:00:00Z"
  }
]
```

---

## POST /v1/experiments

Create a new experiment configuration.

```bash
curl -X POST http://localhost:8000/v1/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sparse_weight_ablation",
    "description": "Test sparse_weight=2.0 on keyword-heavy queries",
    "config": { "sparse_weight": 2.0 }
  }'
```

Queries submitted with `experiment_id` set to this experiment's ID will use the experiment's config overrides. Results are tagged in analytics for comparison.

---

## GET /v1/prompts

List all registered prompt versions.

```bash
curl http://localhost:8000/v1/prompts
```

### Response

```json
[
  {
    "version": "v1",
    "name": "Grounded Strict",
    "description": "Strict grounding prompt; abstains when context is insufficient.",
    "is_active": true,
    "system_prompt": "You are a helpful assistant. Answer using ONLY the provided context. Cite sources as [n]. If the context does not contain the answer, respond: 'I don't have enough information in the provided documents to answer that.'"
  },
  {
    "version": "v2",
    "name": "Grounded with Uncertainty",
    "description": "Like v1 but explicitly states uncertainty when context is partial.",
    "is_active": false,
    "system_prompt": "..."
  }
]
```

Pass `prompt_version` in `/ask` requests to use a non-active prompt version for experimentation.

---

## Error Responses

All errors follow a consistent schema:

```json
{
  "detail": "Human-readable error message or Pydantic validation errors array"
}
```

| HTTP Status | Cause |
|---|---|
| 400 | Bad request (e.g., unsupported file type on ingest) |
| 404 | Resource not found (document ID, evaluation ID) |
| 422 | Pydantic validation failure (missing field, wrong type) |
| 500 | Internal server error (logged with trace) |

---

## Interview Talking Points

- **Why Pydantic v2?** v2's Rust-backed validation core is approximately 5–17× faster than v1 for large response models. The `AskResponse` schema is deeply nested (citations, verifications, trace) — fast serialisation matters at scale.
- **include_trace as optional:** Trace data (all 4 retrieval stage results, each with up to 20 chunks) adds ~50 KB to the response JSON. Making it opt-in keeps normal responses lightweight while giving developers full observability when debugging.
- **SSE over WebSocket for streaming:** SSE is unidirectional, HTTP/1.1 compatible, and trivially proxied by nginx. The platform doesn't need bidirectional communication — streaming tokens from server to client is exactly the SSE use case. WebSocket adds handshake complexity without benefit here.
- **query_id in every response:** Logging `query_id` enables correlation across analytics, evaluation results, and application logs without exposing user PII. Every layer of the system (frontend, backend, Postgres) uses the same UUID.
- **Experiment config overrides:** The experiment system enables runtime A/B testing of retrieval parameters (`sparse_weight`, `rerank_top_k`, etc.) without redeployment. This is essential for data-driven tuning in production.
