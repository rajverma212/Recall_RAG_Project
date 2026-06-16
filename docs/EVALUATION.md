# Evaluation Framework

## Overview

The evaluation framework provides a systematic way to measure retrieval quality, answer correctness, faithfulness, citation accuracy, and confidence calibration across a fixed dataset of 70 examples. It supports side-by-side comparison of chunking strategies and config variants, persists results to PostgreSQL, and generates Markdown and HTML reports. The runner operates fully offline — no external services are required beyond what the platform itself uses.

---

## Dataset

### Location

`evaluation/datasets/eval_set.json` — 70 hand-labelled examples.

### Category Distribution

| Category | Count | Description |
|---|---|---|
| `direct` | 28 | Single-hop questions with a clear factual answer in one chunk |
| `multi_hop` | 17 | Answers requiring synthesis across 2+ chunks or documents |
| `ambiguous` | 13 | Questions where the answer depends on interpretation or context |
| `no_answer` | 12 | Questions intentionally unanswerable from the provided corpus |
| **Total** | **70** | |

### Example structure

```json
{
  "id": "eval_042",
  "category": "multi_hop",
  "question": "What was the candidate's role at Acme Corp and what tech stack did they use?",
  "must_include": ["Senior Engineer", "FastAPI", "PostgreSQL"],
  "relevant_sources": ["resume_v3.pdf"],
  "expected_abstain": false
}
```

Fields:
- `must_include`: keywords or substrings that must appear in a correct answer.
- `relevant_sources`: source files that a correct retrieval must surface.
- `expected_abstain`: if `true`, a correct answer is one where the system abstains.

---

## Metrics

### 1. Retrieval Recall

```
retrieval_recall = |retrieved_sources ∩ relevant_sources| / |relevant_sources|
```

Measures whether the relevant source files appear in the top-`rerank_top_k` retrieved chunks. A chunk is counted as retrieved if its `source_file` matches any entry in `relevant_sources`. Aggregated as mean over all non-`no_answer` examples.

**Why source-file level?** Chunk-level recall is noisier (depends on chunking strategy) and harder to label. Source-file level is stable across chunking configurations and directly reflects whether the retriever found the right document.

### 2. Answer Correctness

For non-`no_answer` examples:

```
answer_correctness = 0.5 × keyword_score + 0.5 × embedding_similarity
```

Where:
- `keyword_score = |must_include terms present in answer| / |must_include|`
- `embedding_similarity = cosine(embed(answer), embed(reference_answer))` (if reference available, else 1.0 when keywords pass)

For `no_answer` examples:

```
answer_correctness = 1.0  if system abstains (answer matches abstention phrase)
                   = 0.0  if system provides any non-abstention answer
```

This binary treatment of `no_answer` is intentional: a confident wrong answer on an unanswerable question is a more serious failure than a hedged partial answer on an answerable one.

### 3. Faithfulness

```
faithfulness = (N_supported + 0.5 × N_partially_supported) / N_total_claims
```

Identical to `citation_accuracy` computed per example (see CITATION_VERIFICATION.md). When DeepEval is installed (`pip install deepeval`), the runner optionally calls DeepEval's `FaithfulnessMetric` as a second opinion. The two scores are reported separately; the platform's own score is the primary metric.

**DeepEval integration:** DeepEval uses an LLM judge internally (configurable; defaults to GPT-4) to decompose answers into atomic claims and check each against the context. It is more thorough than the platform's sentence-level check but significantly more expensive (~10× API cost per example). It is disabled by default and enabled via `--use-deepeval` flag.

### 4. Citation Accuracy

```
citation_accuracy = (N_supported + 0.5 × N_partially_supported) / N_total_claims
```

Same formula as faithfulness but computed from the `verifications` array returned by `RAGService.ask`. Faithfulness measures overall grounding; `citation_accuracy` specifically measures whether cited markers point to chunks that support the claim. The two can diverge when the model writes supported claims without citations (improves faithfulness, lowers citation_accuracy).

### 5. Confidence Calibration (ECE)

Expected Calibration Error (ECE) measures how well the system's confidence scores predict actual correctness.

**Computation:**

1. Divide the 0–100 confidence range into `B` equal bins (default B=10, each bin covers 10 points).
2. For each bin `b`:
   ```
   acc(b) = fraction of examples in bin b that are correct (answer_correctness ≥ threshold)
   conf(b) = mean confidence score of examples in bin b
   ```
3. ECE:
   ```
   ECE = Σ_{b=1}^{B} (|bin_b| / N) × |acc(b) − conf(b)|
   ```
4. Calibration score reported:
   ```
   confidence_calibration = 1 − ECE
   ```

A perfectly calibrated system has `ECE = 0`, meaning answers given 70% confidence are correct 70% of the time. `confidence_calibration = 1.0` is ideal; values above 0.8 indicate good calibration.

**Reliability diagram:** The evaluation report includes a table of (bin, mean_conf, accuracy, count) that can be used to plot a reliability diagram — the standard visualisation for calibration analysis.

| Confidence Bin | Mean Conf | Accuracy | Count |
|---|---|---|---|
| 0–10 | 7.2 | 0.05 | 3 |
| 10–20 | 15.4 | 0.12 | 8 |
| 20–30 | 24.8 | 0.28 | 12 |
| … | … | … | … |
| 90–100 | 94.1 | 0.91 | 11 |

*(Example values — actual values depend on corpus and config.)*

---

## EvaluationRunner

Located at `backend/app/evaluation/runner.py`.

### What it does

1. Loads `eval_set.json` from the dataset path.
2. Ingests a sample corpus (PDF/text files referenced by the eval set) via `RAGService.ingest`.
3. For each example, calls `RAGService.ask` with `include_trace=True`.
4. Computes all five metrics per example.
5. Aggregates metrics over all examples and per category.
6. Persists an `EvaluationRun` record and per-example `EvaluationResult` records to PostgreSQL.
7. Falls back to writing JSON to `evaluation/reports/` if the database is unavailable.
8. Calls `report.py` to generate a Markdown and HTML report.

### Comparison mode

When `--compare` is passed, the runner executes three runs in sequence:
- `chunking_strategy=fixed`
- `chunking_strategy=recursive`
- `chunking_strategy=semantic`

All other config parameters are held constant. A side-by-side comparison table is appended to the report showing metric deltas across strategies.

---

## CLI Usage

All commands run from the project root or inside the backend container.

### Basic run

```bash
python scripts/run_evaluation.py \
  --name "baseline_run_v1" \
  --strategy recursive
```

### Comparison run (all three chunking strategies)

```bash
python scripts/run_evaluation.py \
  --name "chunking_comparison_june" \
  --compare
```

### Run with DeepEval faithfulness

```bash
python scripts/run_evaluation.py \
  --name "deepeval_check" \
  --strategy recursive \
  --use-deepeval
```

### Run inside Docker

```bash
docker compose exec backend python scripts/run_evaluation.py \
  --name "container_run" \
  --strategy fixed
```

### View results via API

```bash
# List all runs
curl http://localhost:8000/v1/evaluations

# Get detailed results for run ID
curl http://localhost:8000/v1/evaluations/<run_id>
```

---

## Reading a Report

Reports are generated at `evaluation/reports/<name>_<timestamp>.md` (and `.html`).

### Report sections

1. **Run summary** — name, date, config snapshot, dataset path.
2. **Aggregate metrics table** — all five metrics as mean over 70 examples.
3. **Per-category metrics table** — metrics broken down by `direct`, `multi_hop`, `ambiguous`, `no_answer`.
4. **Per-example results** — question, answer excerpt, correctness flag, confidence, faithfulness.
5. **Calibration table** — the 10-bin ECE breakdown described above.
6. **Comparison table** (if `--compare`) — side-by-side metric deltas across strategies.
7. **Failure analysis** — examples where `answer_correctness < 0.5` or `citation_accuracy < 0.5`, sorted by confidence to surface overconfident failures first.

### What to look for

| Signal | Interpretation |
|---|---|
| Low `retrieval_recall` on `multi_hop` | Fused top-20 is too small; increase `fusion_top_k` |
| High `answer_correctness`, low `citation_accuracy` | Model answers correctly but doesn't cite; prompt tuning needed |
| `no_answer` correctness < 0.8 | System is not abstaining when it should; lower `min_confidence_to_answer` |
| ECE > 0.15 | Confidence scores not calibrated; recalibrate component weights |
| `semantic` better on `ambiguous` | Semantic chunking preserves context better for ambiguous questions |

---

## Extending the Dataset

New examples should be added to `eval_set.json` following the schema above. Guidelines:

- **`direct` examples**: use questions with a single unambiguous answer in one chunk; `must_include` should have 2–4 keywords.
- **`multi_hop` examples**: the answer must require combining facts from ≥2 source files or sections.
- **`no_answer` examples**: verify manually that the corpus genuinely does not contain the answer; set `expected_abstain: true`.
- Run the evaluation after adding examples to establish a new baseline before making retrieval changes.

---

## Interview Talking Points

- **Why 70 examples?** Small enough to run fully in CI (< 5 minutes offline), large enough to compute stable per-category averages. The category split (direct/multi_hop/ambiguous/no_answer) is more diagnostic than a flat random sample because each category stress-tests a different system capability.
- **ECE vs accuracy:** A system can have high accuracy but poor calibration (always overconfident). ECE catches this and `confidence_calibration = 1 − ECE` makes the metric directionally consistent with the others (higher is better).
- **No-answer evaluation:** Most RAG benchmarks ignore no-answer cases. Treating them as binary (abstain or fail) is strict but correct: in production, a hallucinated answer to an unanswerable question is worse than no answer.
- **Comparison mode design:** Running all three chunking strategies in a single CLI invocation with a shared corpus ensures that differences in retrieval recall are attributable to chunking, not to corpus variation. This is proper ablation methodology.
- **DeepEval as optional:** DeepEval is valuable but expensive (~10× cost per run). Making it opt-in keeps the default evaluation fast and cheap while giving teams a rigorous option for release-gate checks.
