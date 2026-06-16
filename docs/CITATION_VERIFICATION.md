# Citation Verification

## Overview

The citation verification subsystem closes the trust gap in RAG systems. Generation models are prone to hallucination even when grounded context is provided: they may misquote a source, blend two sources, or cite a chunk that does not actually support the claim. This system verifies every cited claim after generation and surfaces the results to users through a citation heatmap and hallucination view in the frontend.

---

## Why Post-Hoc Verification Matters

A naive RAG implementation shows citations as metadata ("answer sourced from document X, chunk Y") but never checks whether the cited text actually supports the generated claim. Users have no way to distinguish a well-grounded answer from a hallucinated one without reading every source chunk manually.

Post-hoc verification:
1. Makes hallucination **visible** rather than hidden.
2. Produces a **quantitative trust signal** (`citation_accuracy`) that feeds the confidence score.
3. Enables the frontend to highlight exactly which sentences are supported, partially supported, or unsupported.
4. Creates an audit trail for regulated use cases (legal, HR, finance).

---

## Stage 1 — Citation Extraction

The generation model is instructed to cite sources using `[n]` markers where `n` is the 1-based index of the context chunk provided in the prompt. The `extract_citations` function parses the generated answer text:

```
Input:  "The candidate achieved 98% test coverage [1] and reduced build time by 40% [2][3]."

Step 1: Regex scan for [n] markers → {[1], [2], [3]}
Step 2: Map marker index → numbered context chunk
Step 3: Find best supporting quote span in the chunk via lexical overlap
         - Tokenise both the sentence and chunk text
         - Sliding window over chunk to find highest token overlap
         - Return the highest-overlap span as `quote`
```

Each extracted citation has the following fields in the API response:

```json
{
  "marker": "[1]",
  "chunk_id": "uuid",
  "document_id": "uuid",
  "source_file": "resume_v3.pdf",
  "page_number": 2,
  "section_title": "Work Experience",
  "quote": "achieved 98% test coverage across the payment service",
  "text": "<full chunk text>"
}
```

The `quote` field is the best-matching substring span from the source chunk, giving users a pinpointed excerpt rather than forcing them to read the entire chunk.

---

## Stage 2 — Per-Claim Verification

The verifier splits the answer into **claims** (one sentence = one claim) and verifies each independently.

### Verification pipeline

```
Answer sentence (claim)
        │
        ▼
  Extract cited [n] markers from the sentence
        │
        ├── No markers found ──► status: unsupported (no citation)
        │
        ▼
  For each cited marker, retrieve the source chunk text
        │
        ▼
  ┌─────────────────────────────────────────────────┐
  │  If OpenAI key available:                        │
  │    LLM judge:                                    │
  │    "Does [chunk text] support [claim]?"           │
  │    → supported | partially_supported | unsupported│
  └───────────────┬─────────────────────────────────┘
                  │  else
  ┌───────────────▼─────────────────────────────────┐
  │  Lexical/embedding fallback:                     │
  │    Token overlap between claim and chunk         │
  │    OR embedding cosine similarity (if model warm)│
  │    Thresholds: >0.5 → supported                  │
  │               0.2–0.5 → partially_supported      │
  │               <0.2 → unsupported                 │
  └─────────────────────────────────────────────────┘
        │
        ▼
  Assign status to claim:
    supported | partially_supported | unsupported
```

### Verification result fields

```json
{
  "claim": "The candidate achieved 98% test coverage.",
  "cited_markers": ["[1]"],
  "status": "supported",
  "rationale": "Source chunk explicitly states '98% test coverage across the payment service'."
}
```

---

## LLM Judge vs Lexical/Embedding Fallback

| Aspect | LLM Judge (OpenAI) | Lexical/Embedding |
|---|---|---|
| Accuracy | High — handles paraphrase, implication | Moderate — misses semantic equivalence |
| Cost | ~0.001 USD per claim verified | Zero |
| Latency | +200–500 ms per answer | < 5 ms |
| Offline capable | No | Yes |
| Handles numeric rounding | Yes (judge reasoning) | No |
| Requirement | `OPENAI_API_KEY` set | Always available |

The LLM judge uses a structured prompt that asks the model to reason about whether the claim is entailed by, partially supported by, or contradicted/absent from the cited chunk. The judge is deliberately conservative: borderline cases are classified `partially_supported` rather than `supported`.

The lexical fallback computes token-level overlap (Jaccard on unigrams after stopword removal). The embedding fallback uses the warm reranker encoder to compute sentence-level cosine similarity. Both fallbacks are used in series (lexical first for speed; embedding if lexical is inconclusive).

---

## Citation Accuracy Formula

```
citation_accuracy = (N_supported + 0.5 × N_partially_supported) / N_total_claims
```

Where:
- `N_supported` = claims with status `supported`
- `N_partially_supported` = claims with status `partially_supported`
- `N_total_claims` = all claims in the answer (including uncited ones)

Uncited sentences count as `unsupported` (numerator contribution = 0), penalising answers that make factual assertions without citing a source. This prevents the model from "hiding" hallucinated claims in uncited sentences.

`citation_accuracy` ranges from 0.0 (every claim unsupported) to 1.0 (every claim fully supported with citations).

---

## Integration with Confidence Score

`citation_accuracy` contributes 30% of the overall confidence score, making it the single largest component:

```
confidence = 100 × (
    0.25 × retrieval_confidence +
    0.25 × reranker_confidence  +
    0.20 × citation_coverage    +
    0.30 × citation_accuracy
)
```

`citation_coverage` (20%) measures the fraction of answer sentences that carry at least one `[n]` marker, independently of whether those citations are verified. Together, `citation_coverage` and `citation_accuracy` account for 50% of the confidence score, reflecting that citation quality is the primary trust signal.

---

## Minimum Confidence Gate

`min_confidence_to_answer = 20` (default). If the computed confidence score falls below this threshold, the system abstains with:

> "I don't have enough information in the provided documents to answer that."

This is the same abstention phrase used when the retriever finds no relevant context. The gate prevents low-confidence guesses from reaching users while remaining permissive enough that genuine partial answers (confidence ~30–50) are still surfaced.

---

## Frontend Consumption

### Citation Heatmap

Each answer sentence is rendered with a background colour indicating its verification status:

| Status | Colour | Meaning |
|---|---|---|
| `supported` | Green | Claim directly supported by cited chunk |
| `partially_supported` | Yellow/Amber | Claim loosely supported; hedging present |
| `unsupported` | Red | No cited chunk supports this claim |
| (no citation) | Grey | Sentence makes no factual claim |

Clicking a highlighted sentence expands the source chunk panel, jumping to the specific `quote` span extracted during citation extraction. This lets users verify the source in one click.

### Hallucination View

A dedicated view lists all `unsupported` and `partially_supported` claims alongside the cited chunk text, enabling reviewers to quickly audit the model's grounding. The view is generated directly from the `verifications` array in the `AskResponse`.

---

## Interview Talking Points

- **Why verify post-hoc rather than constrain generation?** Constrained decoding (e.g., forcing the model to only output tokens present in the context) is too restrictive — it prevents the model from rephrasing or synthesising across chunks. Post-hoc verification preserves generation fluency while adding an independent check layer.
- **The `partially_supported` class:** Binary supported/unsupported classification loses nuance. Many real answers make claims that are directionally correct but imprecise (e.g., "approximately 40%" when the source says "39.7%"). The partial class captures this and weights at 0.5 in the accuracy formula, giving appropriate credit without full endorsement.
- **LLM-as-judge bias:** LLM judges can be too lenient. The system uses a conservative prompt that requires the chunk to explicitly or directly imply the claim; analogical or general-knowledge support is not accepted. This keeps `citation_accuracy` a meaningful signal rather than a rubber stamp.
- **Claim granularity:** Splitting at sentence boundaries is a pragmatic choice. Finer-grained splitting (sub-clauses) would increase sensitivity but also increase API cost proportionally. Sentence-level is the standard in NLI literature (NLI4CT, FEVER) and maps naturally to how humans read answers.
- **Offline completeness:** The system operates fully offline via the lexical/embedding fallback. Quality degrades but the pipeline never hangs waiting for a judge that is unavailable.
