# Evaluation Suite

This directory contains the evaluation infrastructure for the Acme Corp RAG Platform.

## Quick Start

From the **repo root**:

```bash
# 1. (Optional) Seed and ingest the sample corpus into the vector store
python scripts/seed_sample_data.py

# 2. Run evaluation (offline-safe — works without Postgres or Qdrant)
python scripts/run_evaluation.py --name smoke --strategy recursive
```

Reports are written to `evaluation/reports/smoke.md` and `evaluation/reports/smoke.html`.

---

## Directory Structure

```
evaluation/
├── README.md              # This file
├── datasets/
│   └── eval_set.json      # 70 labeled examples across 4 categories
└── reports/               # Generated reports (git-ignored)
    ├── <run_name>.md
    ├── <run_name>.html
    └── comparison.md/.html   (produced by --compare)
```

---

## Running Evaluation

### Basic run

```bash
python scripts/run_evaluation.py --name my_run --strategy recursive
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--name` | `eval` | Human-readable run name |
| `--strategy` | `recursive` | Chunking strategy: `fixed`, `recursive`, `semantic` |
| `--dense-weight` | `1.0` | Weight for dense (vector) retrieval in RRF fusion |
| `--sparse-weight` | `1.0` | Weight for BM25 retrieval in RRF fusion |
| `--dataset` | `evaluation/datasets/eval_set.json` | Path to eval dataset |
| `--compare` | off | Run all strategy/weight combinations and produce comparison |
| `--no-db` | off | Force JSON fallback (skip DB even if available) |
| `--verbose` | off | Print per-example pass/fail to stdout |

### Comparison run

```bash
python scripts/run_evaluation.py --name q1_eval --compare
```

Runs 4 configurations (fixed/recursive × hybrid/dense-only/sparse-only) and writes a side-by-side comparison to `evaluation/reports/comparison.md` and `.html`.

---

## Dataset

`evaluation/datasets/eval_set.json` contains **70 examples** across 4 categories:

| Category | Count | Description |
|----------|-------|-------------|
| `direct` | 28 | Single-hop factual questions with clear answers |
| `multi_hop` | 17 | Questions requiring information from multiple sections/docs |
| `ambiguous` | 13 | Questions with broad scope or requiring synthesis |
| `no_answer` | 12 | Questions not answerable from the corpus (system should abstain) |

Each example has:
- `id`: Unique identifier
- `category`: One of the four categories above
- `question`: The question text
- `expected_answer`: Ground-truth answer (null for `no_answer`)
- `relevant_source_files`: Which corpus files are needed to answer
- `must_include`: Key substrings/facts that must appear in a correct answer

Questions are grounded in the sample corpus (`sample_data/raw/`):
- `employee_handbook.md` — HR policies, benefits, PTO, performance
- `api_reference.md` — DataStream REST API documentation
- `runbook_incidents.txt` — SRE runbooks and incident severity levels
- `security_policy.txt` — Information security policy and data classification
- `onboarding_guide.html` — New employee onboarding (HTML)
- `engineering_standards.md` — Coding standards, Git workflow, testing
- `architecture_overview.md` — System architecture and infrastructure
- `product_roadmap.html` — 2026 product roadmap (HTML)

---

## Metrics

### retrieval_recall
Fraction of relevant source files that appear in the retrieved results.

```
recall = |retrieved ∩ relevant| / |relevant|
```

Returns 1.0 for `no_answer` examples (no relevant files required).

### answer_correctness
Combined keyword + must_include coverage score (0–1).

- **60% weight**: Fraction of `must_include` substrings present in the predicted answer.
- **40% weight**: Word-level token overlap with the expected answer.

For `no_answer` examples: returns 1.0 if the system abstained ("don't have enough information"), 0.0 otherwise.

Optionally uses sentence-transformer embedding similarity if `sentence-transformers` is installed.

### faithfulness
Proportion of claims in the answer that are supported by citations.

```
faithfulness = (supported + 0.5 × partially_supported) / total_claims
```

Optionally uses DeepEval's `FaithfulnessMetric` if available and `use_deepeval=True`.

### citation_accuracy
Stricter than faithfulness — only fully supported claims count.

```
citation_accuracy = supported_claims / total_claims
```

### confidence_calibration
Measures how well the model's confidence scores match actual accuracy.

```
ECE = Σ_b (|b| / N) × |accuracy(b) - confidence(b)|
calibration_score = 1 - ECE
```

Where bins are 10 equal-width intervals on [0, 1].
- **ECE = 0** → perfect calibration → score = 1.0
- **ECE = 1** → worst case → score = 0.0

---

## Pass/Fail Criteria

An example is marked `passed = True` if:
- `retrieval_recall >= 0.5`
- `answer_correctness >= 0.4`
- `faithfulness >= 0.5`

---

## Interpreting Reports

Reports include:
1. **Aggregate metrics table**: Mean scores across all examples.
2. **Per-category table**: Breakdown by category to identify weak spots.
3. **Config snapshot**: Exact settings used for reproducibility.
4. **Per-example table**: Pass/fail and individual scores for every question.

**What to look for**:
- `retrieval_recall < 0.5` → chunking strategy or retrieval weights need tuning.
- `answer_correctness < 0.4` → generation model or prompt version needs improvement.
- `faithfulness < 0.5` → verifier is finding unsupported claims; check retrieved context quality.
- Low `confidence_calibration` → the model is overconfident or underconfident; tune `min_confidence_to_answer`.
- High failure rate in `no_answer` category → system is hallucinating when it should abstain.

---

## Offline Mode

The evaluation suite is designed to run **fully offline**:

- **No OpenAI key**: Embedding uses a deterministic hash-based fallback (`_fake_embed`). Semantic similarity won't work but BM25 and structural matching will.
- **No Qdrant**: Falls back to an in-memory cosine-similarity store.
- **No Postgres**: Skips DB persistence; saves results to `evaluation/reports/<name>_<id>.json` and prints a warning.
- **No DeepEval**: `faithfulness()` uses the rule-based formula.

---

## Adding New Eval Examples

Edit `evaluation/datasets/eval_set.json` and add entries following the schema:

```json
{
  "id": "category_NNN",
  "category": "direct | multi_hop | ambiguous | no_answer",
  "question": "Your question here?",
  "expected_answer": "The correct answer, or null for no_answer",
  "relevant_source_files": ["filename.md"],
  "must_include": ["key phrase", "another fact"]
}
```

Rules:
- `id` must be unique.
- `category` must be one of the four values.
- `no_answer` examples must have `expected_answer: null` and empty `relevant_source_files`.
- `must_include` should contain distinctive facts that distinguish a correct answer from a vague one.
