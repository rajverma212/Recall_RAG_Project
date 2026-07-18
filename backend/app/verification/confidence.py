"""Confidence scoring for RAG responses.

Produces a ConfidenceBreakdown with four component signals and a final score
in [0, 100].

Weight allocation (documented here per spec):
    retrieval_confidence  → 0.25  (how well retrieved chunks match the query)
    reranker_confidence   → 0.25  (mean normalised reranker score for top chunks)
    citation_coverage     → 0.20  (fraction of answer sentences that cite ≥1 source)
    citation_accuracy     → 0.30  (supported/total from verifier, partials = 0.5)

    score = 100 * (0.25 * R + 0.25 * K + 0.20 * C + 0.30 * A)

All four components are in [0, 1] before scaling.
"""
from __future__ import annotations

import re

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.ask import Citation, ClaimVerification, ConfidenceBreakdown

logger = get_logger(__name__)

# ---- Weight constants (must sum to 1.0) ------------------------------------
_W_RETRIEVAL = 0.25
_W_RERANKER = 0.25
_W_COVERAGE = 0.20
_W_ACCURACY = 0.30

assert abs(_W_RETRIEVAL + _W_RERANKER + _W_COVERAGE + _W_ACCURACY - 1.0) < 1e-9

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_MARKER_RE = re.compile(r"\[(\d+)\]")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


def _citation_coverage(answer: str) -> float:
    """Fraction of answer sentences that contain at least one [n] marker."""
    sentences = _split_sentences(answer)
    if not sentences:
        return 0.0
    covered = sum(1 for s in sentences if _MARKER_RE.search(s))
    return covered / len(sentences)


def compute_confidence(
    retrieval_scores: list[float],
    reranker_scores: list[float],
    citations: list[Citation],
    verifications: list[ClaimVerification],
    num_context: int,
    answer: str = "",
    citation_accuracy: float | None = None,
) -> ConfidenceBreakdown:
    """Compute the confidence breakdown.

    Args:
        retrieval_scores:  Fused/dense scores from the RRF stage (raw, not normalised).
        reranker_scores:   Reranker scores already in [0, 1] (sigmoid-normalised).
        citations:         Citations extracted from the answer.
        verifications:     Claim verification results.
        num_context:       Total number of context chunks passed to the generator.
        answer:            The generated answer text (used for coverage calculation).
        citation_accuracy: Pre-computed accuracy from verifier (optional override).

    Returns:
        ConfidenceBreakdown with all four components and the final score.
    """
    # ------------------------------------------------------------------ #
    # 1. Retrieval confidence                                              #
    #    Mean of top-3 retrieval scores, normalised to [0, 1].            #
    #    Retrieval scores from RRF are small positive numbers; we          #
    #    normalise by the theoretical max 1/(k=60+1) * weight=1.0.        #
    # ------------------------------------------------------------------ #
    if retrieval_scores:
        # Normalise against the *theoretical* max RRF score, not the batch's own
        # top score. A chunk ranked #1 by both retrievers scores
        # (dense_weight + sparse_weight) / (rrf_k + 1) (see retrieval/fusion.py);
        # dividing the mean of the top-3 by that anchors confidence to absolute
        # retrieval strength. The old self-normalising form divided by the
        # batch's own top score, which made any single-chunk result score exactly
        # 1.0 and rated three tiny scores (0.001…) the same as three strong ones.
        rrf_max = (settings.dense_weight + settings.sparse_weight) / (settings.rrf_k + 1)
        top_scores = sorted(retrieval_scores, reverse=True)[:3]
        mean_top = sum(top_scores) / len(top_scores)
        retrieval_confidence = min(1.0, mean_top / rrf_max) if rrf_max > 0 else 0.0
    else:
        retrieval_confidence = 0.0

    # ------------------------------------------------------------------ #
    # 2. Reranker confidence                                               #
    #    Mean of reranker scores (already in [0, 1]).                     #
    # ------------------------------------------------------------------ #
    if reranker_scores:
        reranker_confidence = sum(reranker_scores) / len(reranker_scores)
    else:
        reranker_confidence = 0.0

    # ------------------------------------------------------------------ #
    # 3. Citation coverage                                                 #
    # ------------------------------------------------------------------ #
    coverage = _citation_coverage(answer) if answer else (1.0 if citations else 0.0)

    # ------------------------------------------------------------------ #
    # 4. Citation accuracy (from verifier or pre-computed)                #
    # ------------------------------------------------------------------ #
    if citation_accuracy is not None:
        accuracy = max(0.0, min(1.0, citation_accuracy))
    elif verifications:
        weighted = sum(
            1.0 if v.status == "supported"
            else (0.5 if v.status == "partially_supported" else 0.0)
            for v in verifications
        )
        accuracy = weighted / len(verifications)
    else:
        # No verifications: grant partial credit based on whether there are citations
        accuracy = 0.5 if citations else 0.0

    # ------------------------------------------------------------------ #
    # Final weighted score                                                 #
    # ------------------------------------------------------------------ #
    score = 100.0 * (
        _W_RETRIEVAL * retrieval_confidence
        + _W_RERANKER * reranker_confidence
        + _W_COVERAGE * coverage
        + _W_ACCURACY * accuracy
    )
    score = max(0.0, min(100.0, score))

    logger.debug(
        f"Confidence: retrieval={retrieval_confidence:.3f} reranker={reranker_confidence:.3f} "
        f"coverage={coverage:.3f} accuracy={accuracy:.3f} → score={score:.1f}"
    )

    return ConfidenceBreakdown(
        retrieval_confidence=round(retrieval_confidence, 4),
        reranker_confidence=round(reranker_confidence, 4),
        citation_coverage=round(coverage, 4),
        citation_accuracy=round(accuracy, 4),
        score=round(score, 2),
    )
