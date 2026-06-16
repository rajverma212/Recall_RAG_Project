# Ingestion Pipeline

This document describes how uploaded documents are loaded, parsed, deduplicated, embedded, and persisted. The pipeline is implemented in `backend/app/services/ingestion_service.py` and the supporting modules under `backend/app/ingestion/`.

---

## Supported Formats

| Format | Extension(s) | MIME Type(s) | Parser Library | Sectioning Unit |
|--------|-------------|--------------|----------------|-----------------|
| PDF | `.pdf` | `application/pdf` | pypdf `PdfReader` | One section per page |
| Markdown | `.md`, `.markdown` | `text/markdown`, `text/x-markdown` | markdown-it-py | One section per H1/H2/H3 boundary |
| HTML | `.html`, `.htm` | `text/html` | BeautifulSoup4 + lxml | One section per h1–h6 boundary |
| Plain Text | `.txt`, `.text` | `text/plain` | stdlib `re` | One section per blank-line-delimited paragraph |

Type detection (`app/ingestion/detect.py`) checks the file extension first (more specific than MIME), then falls back to the `Content-Type` header. This handles the common case of `text/plain` being sent for both `.txt` and `.md` files — the extension wins.

---

## Metadata Extracted per Section

Every loader produces a list of `LoadedSection` objects. Each section carries:

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `text` | `str` | Extracted content | Stripped of script/style/noscript for HTML |
| `page_number` | `int \| None` | PDF only (1-indexed) | `None` for HTML/Markdown/TXT |
| `section_title` | `str \| None` | Innermost heading text | Heuristic regex for PDF |
| `heading_path` | `str \| None` | Full heading hierarchy | `"H1 > H2 > H3"` style for HTML/MD |
| `ordinal` | `int` | Position in document | 0-indexed, monotonically increasing |

After chunking, each `ChunkPiece` (and the persisted `Chunk` DB row) inherits all of these plus:

| Field | Source |
|-------|--------|
| `source_file` | Original filename from the upload |
| `token_count` | tiktoken cl100k_base (whitespace fallback) |
| `strategy` | `fixed` / `recursive` / `semantic` |
| `chunk_size` | Snapshot of `settings.chunk_size` at ingestion time |
| `chunk_overlap` | Snapshot of `settings.chunk_overlap` at ingestion time |
| `is_duplicate` | Boolean from deduplicator |
| `duplicate_of` | chunk_id of the duplicate source, if applicable |
| `dedup_similarity` | Cosine similarity score that triggered dedup |
| `embedded` | `True` only for non-duplicate chunks |
| `created_at` | UTC timestamp |

The ingestion timestamp is stored on the `Document` row as `ingested_at`.

---

## SHA-256 Idempotency

Before any processing, `IngestionService.ingest_upload()` computes `SHA-256(raw_bytes)`. If a `Document` row already exists with the same hash **and** `status = completed`, the service returns the cached `IngestResponse` immediately without reprocessing.

This guarantees that re-uploading the same file is a no-op, even across application restarts. The idempotency check is at the byte level — identical content under a different filename still deduplicates.

---

## Raw vs Processed Storage Separation

```
/data/
  raw/
    {doc_id}_{filename}        ← original bytes (PDF, HTML, etc.)
  processed/
    {doc_id}.json              ← all ChunkPiece records as JSON
```

**Why separate?** Raw files are the immutable source of truth. If the chunking strategy changes or a bug is found in a loader, the raw file can be re-ingested without re-uploading. Processed JSON is a denormalized cache used for debugging (it includes is_duplicate flags, heading paths, and similarity scores).

The vector store (Qdrant) and Postgres are the authoritative retrieval indexes; the processed JSON is informational only.

---

## Document Status Lifecycle

```
POST /v1/ingest received
        │
        ▼
   [pending] ← default Document.status at row creation
        │
        │  db.flush() — row written, ID committed to session
        ▼
  [processing] ← Document.status set before any I/O
        │
    ┌───┴──────────────────────────────────┐
    │  load → chunk → embed → dedup →      │
    │  upsert Qdrant → write processed.json│
    └───────────────┬──────────────────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
      success               exception
         │                     │
    [completed]            [failed]
    doc.completed_at       doc.error = str(exc)
    doc.num_chunks set     commit attempted; rollback on failure
```

Only `completed` documents are visible in the `/v1/documents` listing and searchable via retrieval. The `failed` status with the error string is surfaced in the API so operators can diagnose format issues without inspecting logs.

---

## Sequence Diagram: `ingest_upload`

```
Client          API Layer       IngestionService      Loaders       Chunker      EmbeddingClient   Deduplicator   VectorStore   Postgres
  │                │                  │                  │              │               │                │              │            │
  │─POST /ingest──►│                  │                  │              │               │                │              │            │
  │                │──ingest_upload──►│                  │              │               │                │              │            │
  │                │                  │─detect_doc_type─►│              │               │                │              │            │
  │                │                  │─sha256(bytes)────────────────────────────────────────────────────────────────────────────────►│
  │                │                  │◄─────────────────────────────────────────────── existing? ───────────────────────────────────│
  │                │                  │  (if exists → return early)                                                                   │
  │                │                  │─write raw bytes to /data/raw/                                                                │
  │                │                  │─create Document(status=processing)────────────────────────────────────────────────────────── ►│
  │                │                  │─get_loader(doc_type)─►│              │               │                │              │        │
  │                │                  │◄─loader.load(bytes)───│              │               │                │              │        │
  │                │                  │─get_chunker(strategy)───────────────►│               │                │              │        │
  │                │                  │◄─chunker.chunk(sections)─────────────│               │                │              │        │
  │                │                  │─embed([texts])───────────────────────────────────────►               │              │        │
  │                │                  │◄─EmbeddingResult(vectors, tokens)────────────────────               │              │        │
  │                │                  │─dedup.check(chunk_ids, texts, vectors)──────────────────────────────►              │        │
  │                │                  │◄─[(is_dup, dup_of, sim), ...]─────────────────────────────────────────             │        │
  │                │                  │─upsert(non_dup_ids, vectors, payloads)───────────────────────────────────────────── ►       │
  │                │                  │─write /data/processed/{doc_id}.json                                                │        │
  │                │                  │─update Document(status=completed)─────────────────────────────────────────────────────────── ►│
  │                │◄─IngestResponse──│                                                                                               │
  │◄───200 JSON────│                  │                                                                                               │
```

---

## Loader Implementation Details

### PDF Loader (`loaders/pdf_loader.py`)
Uses `pypdf.PdfReader`. Iterates pages starting at index 1. Empty pages (no extractable text) are skipped with a debug log. Section title is extracted via a heuristic regex: the first line that starts with an uppercase letter or digit and is ≤120 characters — intentionally simple to avoid false positives on body text.

### Markdown Loader (`loaders/markdown_loader.py`)
Parses with `markdown_it.MarkdownIt().parse()` to obtain a token stream. Sections are flushed at `heading_open` tokens. The heading stack tracks the full path (e.g. `"Introduction > Background"`) and is pruned when a heading of equal or higher level is encountered. Fenced code blocks (`fence`, `code_block` tokens) are captured verbatim in the buffer. If the document has no headings at all, the entire inline content is emitted as one section.

### HTML Loader (`loaders/html_loader.py`)
Parses with `BeautifulSoup(html, "lxml")`. Removes `<script>`, `<style>`, `<noscript>`, `<meta>`, and `<head>` before walking `body.descendants`. Heading elements (h1–h6) flush the current text buffer and update the heading stack. Text is joined with spaces (not newlines) to handle inline-split text nodes. Falls back to `body.get_text()` if no sections are found.

### TXT Loader (`loaders/txt_loader.py`)
Splits on `\n\s*\n` (blank lines). Each paragraph becomes one `LoadedSection` with no heading metadata. If the file contains no blank lines, the entire file is treated as one section. No heuristic title extraction is attempted for plain text.

---

## Deduplication

The `Deduplicator` class performs two-pass cosine similarity checking after embedding:

1. **Within-batch**: For each new chunk, dot-product similarity is computed against all previously accepted chunks in the current upload. This prevents near-identical sections within a single document from being indexed twice.

2. **Cross-document**: The vector store is queried (`top_k=1`) to find the nearest existing vector across all previously ingested documents. If the returned score exceeds `dedup_cosine_threshold` (default **0.95**), the chunk is marked as a duplicate.

Vectors are L2-normalised before storage, so cosine similarity equals the dot product — efficient to compute without materialising a norm.

Duplicates are recorded in Postgres (`is_duplicate=True`, `duplicate_of`, `dedup_similarity`) but are **not** upserted to Qdrant. This means they are invisible to retrieval but auditable via the DB.

Deduplication can be disabled per-deployment with `DEDUP_ENABLED=false`.

---

## Trade-offs: Per-Page vs Per-Section Sectioning

| Approach | Used By | Pros | Cons |
|----------|---------|------|------|
| **Per-page** | PDF | Preserves visual layout boundaries; page numbers are meaningful in citations | Page boundaries are arbitrary — a table may split across pages; long pages become oversized sections |
| **Per-section (heading-based)** | HTML, Markdown | Sections align with semantic document structure; heading paths enable precise citations | Requires well-formed heading hierarchy; flat documents become one giant section |
| **Per-paragraph** | TXT | Robust fallback with no structural assumptions | Loses all hierarchical context; cannot produce heading paths |

**Why PDF uses per-page rather than per-section:** pypdf extracts raw text strings without layout metadata — it cannot reliably identify whether a line is a heading vs. body text. The heuristic regex (`_HEADING_RE`) attempts a best-effort title, but it is not used for structural splitting. Per-page splitting gives deterministic, bounded section sizes. For documents with very long pages (e.g., single-page policy documents), the downstream chunker then handles the splitting.

> **Interview talking point:** The loader-chunker separation is deliberate. Loaders produce coarse semantic units (pages / sections / paragraphs); chunkers produce fine-grained retrieval units. This means you can swap chunking strategies without re-running loaders, and per-loader logic stays focused on format concerns.

---

## Design Rationale

- **Single transaction per document**: The entire pipeline runs inside a `db.flush()` → (processing) → `db.commit()` (completed) pair. On any exception, `status=failed` and `error=str(exc)` are committed, ensuring the DB always reflects the true outcome.
- **Batch embedding**: All chunks from a document are embedded in one API call to minimise round-trips and latency.
- **Raw bytes kept**: Storing the original file allows re-ingestion with a different chunking strategy without requiring the user to re-upload. The SHA-256 check prevents re-ingestion of unchanged content.
- **Dedup after embedding, not before**: Text-level dedup (e.g., exact SHA-256 of chunk text) would miss semantically identical text with minor formatting differences. Cosine-similarity dedup catches near-paraphrase and OCR noise.
