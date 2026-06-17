"""Evaluation metrics for the RAG pipeline.

Metrics implemented:
- retrieval_recall           : fraction of relevant source files that were retrieved
- answer_correctness         : keyword/substring coverage + no_answer handling
- faithfulness               : fraction of claims supported by citations (with optional DeepEval)
- citation_accuracy          : fraction of verifications that are "supported"
- confidence_calibration     : 1 - ECE (Expected Calibration Error) over equal-width bins

Math notes — confidence_calibration
------------------------------------
ECE is calculated over B equal-width bins partitioning [0, 1]:

    ECE = Σ_b  (|b| / N) * |accuracy(b) - confidence(b)|

where:
  |b|            = number of samples in bin b
  N              = total samples
  accuracy(b)    = fraction of samples in bin b that are correct (passed=True)
  confidence(b)  = mean predicted confidence in bin b (values ∈ [0, 1])

Perfect calibration → ECE = 0 → calibration_score = 1.
Worst case ECE = 1 → calibration_score = 0.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Retrieval Recall
# ---------------------------------------------------------------------------

def retrieval_recall(
    retrieved_source_files: list[str],
    relevant_source_files: list[str],
) -> float:
    """Compute recall: fraction of relevant files actually retrieved.

    Args:
        retrieved_source_files: filenames returned by the retrieval pipeline.
        relevant_source_files:  ground-truth filenames for this question.

    Returns:
        Float in [0.0, 1.0].  Returns 1.0 if relevant_source_files is empty
        (vacuously true — the question has no required sources).
    """
    if not relevant_source_files:
        return 1.0
    relevant_set = set(relevant_source_files)
    retrieved_set = set(retrieved_source_files)
    hits = len(relevant_set & retrieved_set)
    return hits / len(relevant_set)


# ---------------------------------------------------------------------------
# Answer Correctness
# ---------------------------------------------------------------------------

_ABSTENTION_PHRASES = [
    "don't have enough information",
    "do not have enough information",
    "don't have information",
    "not enough information",
    "cannot answer",
    "no information available",
    "i don't know",
    "i do not know",
    "the documents do not contain",
    "not found in the provided",
    "unable to answer",
    "information is not available",
    "not available in the",
]


def _is_abstention(answer: str) -> bool:
    """Return True when the model abstained from answering."""
    lower = answer.lower()
    return any(phrase in lower for phrase in _ABSTENTION_PHRASES)


def _keyword_overlap(predicted: str, expected: str, must_include: list[str]) -> float:
    """Compute a combined keyword / must_include coverage score.

    Strategy:
    1. must_include substrings each contribute equally when present (weight 0.6).
    2. Word-level overlap between predicted and expected tokens (weight 0.4).

    Returns float in [0.0, 1.0].
    """
    pred_lower = predicted.lower()

    # --- Must-include coverage (60% weight) ---
    if must_include:
        hits = sum(
            1
            for kw in must_include
            if kw.lower() in pred_lower
        )
        must_score = hits / len(must_include)
    else:
        must_score = 1.0  # no must_include → full credit on this dimension

    # --- Word overlap (40% weight) ---
    def tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    pred_tokens = tokenize(predicted)
    exp_tokens = tokenize(expected)
    if exp_tokens:
        overlap = len(pred_tokens & exp_tokens) / len(exp_tokens)
    else:
        overlap = 1.0

    return 0.6 * must_score + 0.4 * overlap


def answer_correctness(
    predicted: str,
    expected: str | None,
    must_include: list[str],
) -> float:
    """Score the predicted answer against the expected answer.

    For no_answer examples (expected is None):
        Returns 1.0 if the system abstained ("don't have enough information")
        Returns 0.0 otherwise.

    For all other examples:
        Returns a float in [0.0, 1.0] based on keyword/substring matching
        against expected_answer and must_include key facts.

    Optionally uses embedding similarity if sentence-transformers is available,
    but falls back gracefully to keyword matching alone.

    Args:
        predicted:    The model's answer string.
        expected:     Ground-truth answer, or None for no_answer examples.
        must_include: List of key substrings that must appear in the answer.

    Returns:
        Float in [0.0, 1.0].
    """
    if predicted is None:
        predicted = ""

    # No-answer case
    if expected is None:
        return 1.0 if _is_abstention(predicted) else 0.0

    if not predicted.strip():
        return 0.0

    # Keyword / substring score
    kw_score = _keyword_overlap(predicted, expected, must_include)

    # Optional: embedding similarity boost
    try:
        from sentence_transformers import util  # type: ignore
        _model = _get_sentence_model()
        if _model is not None:
            emb_pred = _model.encode(predicted, convert_to_tensor=True)
            emb_exp = _model.encode(expected, convert_to_tensor=True)
            cos_sim = float(util.cos_sim(emb_pred, emb_exp)[0][0])
            cos_sim = max(0.0, cos_sim)
            # Blend: 60% keyword, 40% semantic
            return 0.6 * kw_score + 0.4 * cos_sim
    except Exception:
        pass

    return kw_score


_sentence_model = None
_sentence_model_loaded = False


def _get_sentence_model():
    global _sentence_model, _sentence_model_loaded
    if _sentence_model_loaded:
        return _sentence_model
    _sentence_model_loaded = True
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _sentence_model = None
    return _sentence_model


# ---------------------------------------------------------------------------
# Faithfulness
# ---------------------------------------------------------------------------

def faithfulness(
    verifications: list,
    use_deepeval: bool = False,
    actual_output: str | None = None,
    retrieval_context: list[str] | None = None,
) -> float:
    """Compute faithfulness from claim verification statuses.

    Formula (rule-based):
        score = (supported + 0.5 * partially_supported) / total_claims

    Optionally delegates to DeepEval's FaithfulnessMetric if available and
    use_deepeval=True.

    Args:
        verifications:     list of ClaimVerification objects (have .status attribute).
        use_deepeval:      if True, attempt to use DeepEval (requires API key + internet).
        actual_output:     the model answer string (needed for DeepEval).
        retrieval_context: list of retrieved chunk texts (needed for DeepEval).

    Returns:
        Float in [0.0, 1.0].  Returns 1.0 if no verifications (vacuous).
    """
    if not verifications:
        return 1.0

    if use_deepeval:
        try:
            from deepeval.metrics import FaithfulnessMetric  # type: ignore
            from deepeval.test_case import LLMTestCase  # type: ignore

            metric = FaithfulnessMetric(threshold=0.5)
            test_case = LLMTestCase(
                input="",
                actual_output=actual_output or "",
                retrieval_context=retrieval_context or [],
            )
            metric.measure(test_case)
            return float(metric.score)
        except Exception:
            pass  # Fall through to rule-based

    # Rule-based
    supported = sum(1 for v in verifications if v.status == "supported")
    partial = sum(1 for v in verifications if v.status == "partially_supported")
    total = len(verifications)
    return (supported + 0.5 * partial) / total


# ---------------------------------------------------------------------------
# Citation Accuracy
# ---------------------------------------------------------------------------

def citation_accuracy(verifications: list) -> float:
    """Fraction of claims that are fully supported (not merely partial).

    This is stricter than faithfulness: partial = 0, not 0.5.

    Args:
        verifications: list of ClaimVerification objects.

    Returns:
        Float in [0.0, 1.0].  Returns 1.0 if no verifications.
    """
    if not verifications:
        return 1.0
    supported = sum(1 for v in verifications if v.status == "supported")
    return supported / len(verifications)


# ---------------------------------------------------------------------------
# Confidence Calibration
# ---------------------------------------------------------------------------

def confidence_calibration(
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 10,
) -> float:
    """Compute calibration score as 1 - ECE (Expected Calibration Error).

    ECE measures how well predicted confidence scores match actual accuracy.
    A perfectly calibrated model has ECE=0 (score=1.0).

    Math:
        ECE = Σ_{b=1}^{B}  (|b| / N) * |acc(b) - conf(b)|

    where B=n_bins equal-width bins on [0, 1].

        acc(b)  = mean(correct) for samples in bin b
        conf(b) = mean(confidence) for samples in bin b

    Args:
        confidences: list of confidence values in [0, 1].
        correct:     list of bool indicating whether the answer was correct (passed).
        n_bins:      number of equal-width bins (default 10).

    Returns:
        Float in [0.0, 1.0] where 1.0 = perfectly calibrated.
        Returns 1.0 if the list is empty (degenerate case).
    """
    if not confidences or not correct:
        return 1.0

    assert len(confidences) == len(correct), (
        f"confidences ({len(confidences)}) and correct ({len(correct)}) must have same length"
    )

    n = len(confidences)
    bin_size = 1.0 / n_bins

    ece = 0.0
    for b in range(n_bins):
        lo = b * bin_size
        hi = lo + bin_size
        # Upper edge inclusive for last bin
        if b == n_bins - 1:
            indices = [i for i, c in enumerate(confidences) if lo <= c <= hi]
        else:
            indices = [i for i, c in enumerate(confidences) if lo <= c < hi]

        if not indices:
            continue

        bin_conf = sum(confidences[i] for i in indices) / len(indices)
        bin_acc = sum(1.0 for i in indices if correct[i]) / len(indices)
        ece += (len(indices) / n) * abs(bin_acc - bin_conf)

    return max(0.0, 1.0 - ece)
