# Chunking Strategies

Chunking is the step between document loading and embedding. It determines the granularity of retrieval units: too coarse and irrelevant content dilutes the context; too fine and key context is split across multiple chunks. This document covers the three implemented strategies, their configuration, and guidance on when to use each.

---

## Overview

The chunker receives a list of `LoadedSection` objects from a loader and returns a flat list of `ChunkPiece` objects. Chunkers are selected at ingest time via the `strategy` query parameter (or the `CHUNKING_STRATEGY` environment variable, default: `recursive`).

```python
# app/chunking/base.py
@dataclass
class ChunkPiece:
    text: str
    ordinal: int         # document-level ordering
    token_count: int     # tiktoken cl100k_base count
    page_number: int | None
    section_title: str | None
    heading_path: str | None
```

Token counting uses `tiktoken.get_encoding("cl100k_base")` — the same tokenizer used by OpenAI's embedding and generation models — with a whitespace-split word count as a fallback when tiktoken is unavailable.

---

## Strategy 1: Fixed-Size (`fixed`)

**File:** `backend/app/chunking/fixed.py`

### How it works

The input section text is tokenized to a list of BPE tokens. A sliding window of `chunk_size` tokens is stepped through the token list, with each step advancing by `chunk_size - chunk_overlap` tokens.

```
tokens: [t0 t1 t2 t3 t4 t5 t6 t7 t8 t9]
chunk_size=5, chunk_overlap=2

Chunk 0: [t0 t1 t2 t3 t4]
Chunk 1: [t3 t4 t5 t6 t7]   ← starts at idx = end - overlap = 3
Chunk 2: [t6 t7 t8 t9]      ← last window (may be shorter)
```

The tokenizer used is `tiktoken` cl100k_base; `_detokenize()` reconstructs the string by concatenating the decoded token strings (BPE tokens are byte-level, so joining preserves whitespace faithfully).

### When to use

- Tabular data, code files, or documents where logical boundaries are not expressed by paragraphs or headings.
- When you want guaranteed uniform chunk sizes for analysis or benchmarking.
- When predictable memory usage is required (fixed-size windows are O(1) in extra space per chunk).

---

## Strategy 2: Recursive (`recursive`) — Default

**File:** `backend/app/chunking/recursive.py`

### How it works

This strategy mirrors LangChain's `RecursiveCharacterTextSplitter` but without the LangChain dependency. It splits on a prioritized separator hierarchy, trying each separator in order and recursing on sub-pieces that are still too large:

```python
_DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
```

**Algorithm (simplified):**

```
function split_recursive(text, separators, chunk_size):
    if token_count(text) <= chunk_size:
        return [text]                   # base case — fits already

    sep = separators[0]
    parts = text.split(sep)
    buffer = []
    buffer_tokens = 0

    for part in parts:
        if token_count(part) > chunk_size:
            flush(buffer)               # flush whatever is buffered
            sub_chunks = split_recursive(part, separators[1:], chunk_size)
            extend(sub_chunks)          # recurse with next separator
        elif buffer_tokens + token_count(part) > chunk_size:
            flush(buffer)               # flush and start new buffer
            buffer = [part]
        else:
            buffer.append(part)         # accumulate

    flush(buffer)
```

**Separator priority explained:**

| Priority | Separator | Rationale |
|----------|-----------|-----------|
| 1 | `\n\n` | Paragraph boundary — highest semantic value |
| 2 | `\n` | Line break — often marks list items, headings |
| 3 | `. ` | Sentence boundary |
| 4 | ` ` | Word boundary |
| 5 | `""` | Character split (last resort) |

After splitting, `_add_overlap()` prepends up to `chunk_overlap` words from the end of the previous chunk to the beginning of each subsequent chunk. This is an approximate word-level overlap (not token-level) but is fast and avoids re-tokenizing.

### When to use

- General-purpose use on prose documents (technical docs, reports, policies).
- When the document has inconsistent heading structure or mixed content.
- The default for most production use cases because it preserves sentence and paragraph integrity far better than fixed splitting.

---

## Strategy 3: Semantic (`semantic`)

**File:** `backend/app/chunking/semantic.py`

### How it works

Semantic chunking uses embedding-based similarity to find natural topic transitions in the text.

**Step-by-step:**

1. **Sentence splitting**: The section text is split on sentence boundaries (`(?<=[.!?])\s+`).
2. **Sentence embedding**: All sentences are embedded in a single batch call via `EmbeddingClient.embed()`.
3. **Consecutive distance**: Cosine distance is computed between each adjacent pair of sentence embeddings. Because vectors are L2-normalised, cosine distance = 1 − dot product.
4. **Breakpoint detection**: The `semantic_breakpoint_percentile`-th percentile (default **95.0**) of the distance distribution is computed. Any consecutive pair whose distance exceeds this threshold is a breakpoint.
5. **Grouping**: Sentences are accumulated into a chunk until a breakpoint is reached **or** the token count exceeds `chunk_size` (soft cap). When either condition fires, the current group is flushed as a chunk.

```
sentences:   [S0] [S1] [S2] [S3] [S4] [S5]
distances:        0.08 0.07 0.41 0.09 0.06
95th pct threshold = 0.35

breakpoints at: dist[S2→S3]=0.41 >= 0.35

chunk A: S0 S1 S2
chunk B: S3 S4 S5
```

**Cost implication**: Unlike fixed and recursive, the semantic chunker calls the embedding API **at ingestion time** for every sentence in every section. With `text-embedding-3-small` at $0.02/1M tokens, a 100-page PDF with ~5000 sentences (~150K tokens) costs ~$0.003 extra in embedding calls. Not significant for single documents but adds up with bulk ingestion.

If fewer than 2 sentences are present in a section, a breakpoint cannot be computed and the section is emitted as a single chunk.

### When to use

- Long, dense documents where topics shift within sections (e.g., research papers, legal contracts).
- When retrieval quality is the top priority and ingestion throughput is secondary.
- Multi-topic documents where fixed/recursive would produce chunks that span unrelated topics.

---

## Configuration Knobs

All three strategies read from `app/core/config.py`:

| Env Var | Setting | Default | Effect |
|---------|---------|---------|--------|
| `CHUNKING_STRATEGY` | `chunking_strategy` | `recursive` | Strategy used when not specified per-upload |
| `CHUNK_SIZE` | `chunk_size` | `512` | Target token count per chunk |
| `CHUNK_OVERLAP` | `chunk_overlap` | `64` | Overlap token/word budget between chunks |
| `SEMANTIC_BREAKPOINT_PERCENTILE` | `semantic_breakpoint_percentile` | `95.0` | How aggressively to split on semantic boundaries |

The strategy can be overridden per-upload via the `?strategy=` query parameter on `POST /v1/ingest`, which allows comparing strategies on the same document.

---

## Metadata Persisted per Chunk

Every `Chunk` row in Postgres carries the full provenance snapshot:

```
chunks table columns (relevant):
  id, document_id, text, token_count, ordinal
  source_file, page_number, section_title, heading_path
  strategy, chunk_size, chunk_overlap           ← config snapshot
  is_duplicate, duplicate_of, dedup_similarity  ← dedup audit
  embedded, created_at
```

The `strategy`, `chunk_size`, and `chunk_overlap` values are snapshotted at ingestion time. This means a document ingested with `chunk_size=512` still has its chunks correctly described even if the system default is later changed to 256. The evaluation framework can therefore group and compare results across configurations precisely.

---

## Comparison Table

| Dimension | Fixed | Recursive | Semantic |
|-----------|-------|-----------|---------|
| Chunk size predictability | Exact | Approximate (≤ chunk_size) | Variable (content-driven) |
| Sentence/paragraph preservation | No | Yes (tries `\n\n` → `\n` → `. ` first) | Yes (splits at topic shifts) |
| Extra API calls at ingestion | None | None | Yes (sentence embeddings) |
| Handles headings | Ignores | Ignores (structural info comes from loader) | Ignores |
| Best for | Tabular / code | General prose | Dense multi-topic prose |
| Overlap mechanism | Token-exact | Word-approximate | None (natural breakpoints) |
| Reproducible without API key | Yes | Yes | No (needs embed) |

---

## How Chunking Affects Retrieval Quality

**Chunk size vs. retrieval precision vs. recall:**
- **Smaller chunks** → higher precision (retrieved text is tightly focused) but lower recall (a query spanning two paragraphs may not match either chunk well).
- **Larger chunks** → higher recall (more context per unit) but lower precision (irrelevant sentences dilute embedding similarity and waste the LLM context window).
- The 512-token default is in the empirical sweet spot for most technical documentation (SBERT and OpenAI research show similar recommendations).

**Overlap prevents boundary misses:** Without overlap, a query whose key term appears at the end of chunk A and the beginning of chunk B may not match either strongly. Overlap ensures the 64-token boundary region is present in both consecutive chunks.

**Recursive > fixed for prose:** Fixed splitting at token boundaries can cut mid-sentence or mid-phrase, producing semantically incoherent chunks. Recursive splitting at `\n\n` first ensures that in most documents, chunk boundaries align with paragraph breaks.

**Semantic chunking and BM25:** The semantic chunker produces variable-length chunks that may be shorter than the configured `chunk_size`. This can weaken BM25 retrieval because shorter chunks have lower IDF-weighted term frequencies. The fixed and recursive strategies produce more uniform chunk sizes that behave more predictably with BM25.

> **Interview talking point:** A common interview question is "how do you choose chunk size?" The honest answer is: it depends on your embedding model's effective context window (for `text-embedding-3-small`, ~8192 tokens is the hard limit, but semantic quality degrades well before that), your typical query length, and your answer synthesis target. You measure this empirically with a retrieval recall metric on a held-out question set — which is exactly what the evaluation framework in this system supports.
