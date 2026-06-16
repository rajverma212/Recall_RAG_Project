"""Post-generation claim verification.

Pipeline:
1. Split the answer into individual claims (sentences).
2. For each claim, identify its cited [n] markers.
3. Verify whether the cited chunk text supports the claim:
   - If OpenAI key is present, use LLM judge (gpt-4o-mini, cheap).
   - Otherwise, use lexical overlap (Jaccard on words):
       supported:            overlap >= HIGH_THRESHOLD
       partially_supported:  overlap >= LOW_THRESHOLD
       unsupported:          overlap < LOW_THRESHOLD or no citation

Also computes citation_accuracy:
    accuracy = (supported_count + 0.5 * partial_count) / total_claims
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.ask import Citation, ClaimVerification

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

_MARKER_RE = re.compile(r"\[(\d+)\]")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")

# Lexical thresholds (Jaccard)
HIGH_THRESHOLD = 0.15   # word overlap fraction → "supported"
LOW_THRESHOLD = 0.05    # word overlap fraction → "partially_supported"


def _split_claims(answer: str) -> list[str]:
    """Split an answer into atomic claims (sentences).

    Sentences that consist only of [n] markers (no substantive text) are
    merged into the preceding sentence so that citations trailing a period
    are associated with their claim rather than forming orphan fragments.
    """
    raw = [s.strip() for s in _SENT_RE.split(answer) if s.strip()]
    # Merge marker-only fragments into the preceding sentence
    merged: list[str] = []
    _ONLY_MARKERS = re.compile(r"^(\[\d+\]\s*)+$")
    for part in raw:
        if _ONLY_MARKERS.match(part) and merged:
            merged[-1] = merged[-1] + " " + part
        else:
            merged.append(part)
    return merged


def _words(text: str) -> set[str]:
    return set(re.findall(r"\b\w+\b", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union)


def _lexical_verify(claim: str, chunk_text: str) -> float:
    """Return Jaccard overlap between claim words and chunk words (0-1)."""
    # Remove citation markers from claim for cleaner comparison
    claim_clean = _MARKER_RE.sub("", claim)
    return _jaccard(_words(claim_clean), _words(chunk_text))


def _llm_verify(claim: str, evidence: str) -> tuple[str, str]:
    """Ask the LLM to judge whether the evidence supports the claim.

    Returns (status, rationale).
    """
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        "Does the EVIDENCE support the CLAIM?\n"
        f"CLAIM: {claim}\n"
        f"EVIDENCE: {evidence}\n\n"
        "Reply with exactly one line: SUPPORTED, PARTIALLY_SUPPORTED, or UNSUPPORTED, "
        "followed by a pipe and a one-sentence rationale.\n"
        "Example: SUPPORTED | The evidence directly states X."
    )
    try:
        resp = client.chat.completions.create(
            model=settings.generation_model,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
        )
        raw = (resp.choices[0].message.content or "").strip()
        parts = raw.split("|", 1)
        status_str = parts[0].strip().upper()
        rationale = parts[1].strip() if len(parts) > 1 else raw

        status_map = {
            "SUPPORTED": "supported",
            "PARTIALLY_SUPPORTED": "partially_supported",
            "UNSUPPORTED": "unsupported",
        }
        status = status_map.get(status_str, "unsupported")
        return status, rationale
    except Exception as exc:
        logger.warning(f"LLM verifier failed, falling back to lexical: {exc}")
        raise


def verify(
    answer: str,
    citations: list[Citation],
    context_chunks: list[dict] | None = None,
) -> tuple[list[ClaimVerification], float]:
    """Verify each claim in *answer* against its cited passages.

    Args:
        answer:         The generated answer (may contain [n] markers).
        citations:      Citation objects extracted from the answer.
        context_chunks: Optional list of dicts with 'text' and chunk metadata;
                        if None, chunk text is taken from the Citation.text field.

    Returns:
        (verifications, citation_accuracy)
        citation_accuracy = (supported + 0.5 * partial) / total_claims
    """
    # Build marker → chunk text mapping
    marker_to_text: dict[int, str] = {}
    for cit in citations:
        marker_to_text[cit.marker] = cit.text

    claims = _split_claims(answer)
    if not claims:
        return [], 1.0

    use_llm = bool(settings.openai_api_key)
    verifications: list[ClaimVerification] = []

    for claim in claims:
        markers = [int(m) for m in _MARKER_RE.findall(claim)]
        # Filter to markers that have a known citation
        cited_markers = [m for m in markers if m in marker_to_text]

        if not cited_markers:
            verifications.append(
                ClaimVerification(
                    claim=claim,
                    cited_markers=[],
                    status="unsupported",
                    rationale="No citation markers found for this claim.",
                )
            )
            continue

        # Aggregate evidence from all cited chunks
        evidence_texts = [marker_to_text[m] for m in cited_markers]
        combined_evidence = " ".join(evidence_texts)

        if use_llm:
            try:
                status, rationale = _llm_verify(claim, combined_evidence)
                verifications.append(
                    ClaimVerification(
                        claim=claim,
                        cited_markers=cited_markers,
                        status=status,
                        rationale=rationale,
                    )
                )
                continue
            except Exception:
                pass  # fall through to lexical

        # Lexical overlap heuristic
        overlap = _lexical_verify(claim, combined_evidence)
        if overlap >= HIGH_THRESHOLD:
            status = "supported"
            rationale = f"Lexical overlap with cited passage(s): {overlap:.2f}"
        elif overlap >= LOW_THRESHOLD:
            status = "partially_supported"
            rationale = f"Partial lexical overlap with cited passage(s): {overlap:.2f}"
        else:
            status = "unsupported"
            rationale = f"Low lexical overlap with cited passage(s): {overlap:.2f}"

        verifications.append(
            ClaimVerification(
                claim=claim,
                cited_markers=cited_markers,
                status=status,
                rationale=rationale,
            )
        )

    # Compute citation accuracy
    total = len(verifications)
    if total == 0:
        return verifications, 0.0

    weighted = sum(
        1.0 if v.status == "supported" else (0.5 if v.status == "partially_supported" else 0.0)
        for v in verifications
    )
    citation_accuracy = weighted / total

    return verifications, citation_accuracy
