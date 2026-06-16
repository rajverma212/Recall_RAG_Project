"""Post-generation claim verification.

Pipeline:
1. Split the answer into atomic claims (sentences).
2. For each claim, identify its cited [n] markers and gather the cited chunk text.
3. Ask the active LLM provider whether the evidence supports the claim
   (``provider.verify_citation``) → supported / partially_supported / unsupported.
   The provider abstracts the backend: Anthropic/OpenAI judge online, the Local
   provider uses a lexical-overlap heuristic offline.

citation_accuracy = (supported + 0.5 * partial) / total_claims
"""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.providers.factory import get_llm_provider
from app.schemas.ask import Citation, ClaimVerification

logger = get_logger(__name__)

_MARKER_RE = re.compile(r"\[(\d+)\]")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_ONLY_MARKERS = re.compile(r"^(\[\d+\]\s*)+$")


def _split_claims(answer: str) -> list[str]:
    """Split into sentences; merge marker-only fragments into the prior sentence."""
    raw = [s.strip() for s in _SENT_RE.split(answer) if s.strip()]
    merged: list[str] = []
    for part in raw:
        if _ONLY_MARKERS.match(part) and merged:
            merged[-1] = merged[-1] + " " + part
        else:
            merged.append(part)
    return merged


def verify(
    answer: str,
    citations: list[Citation],
    context_chunks: list[dict] | None = None,
) -> tuple[list[ClaimVerification], float]:
    """Verify each claim against its cited passages via the active provider."""
    marker_to_text = {cit.marker: cit.text for cit in citations}
    claims = _split_claims(answer)
    if not claims:
        return [], 1.0

    provider = get_llm_provider()
    verifications: list[ClaimVerification] = []

    for claim in claims:
        markers = [int(m) for m in _MARKER_RE.findall(claim)]
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

        evidence = " ".join(marker_to_text[m] for m in cited_markers)
        try:
            verdict = provider.verify_citation(claim, evidence)
            status, rationale = verdict.status, verdict.rationale
        except Exception as exc:  # provider failure → conservative default
            logger.warning(f"verify_citation failed ({exc}); marking unsupported")
            status, rationale = "unsupported", "Verification failed."

        verifications.append(
            ClaimVerification(
                claim=claim,
                cited_markers=cited_markers,
                status=status,
                rationale=rationale,
            )
        )

    total = len(verifications)
    weighted = sum(
        1.0 if v.status == "supported" else (0.5 if v.status == "partially_supported" else 0.0)
        for v in verifications
    )
    return verifications, (weighted / total if total else 0.0)
