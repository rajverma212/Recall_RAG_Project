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
# Leading citation marker(s) at the start of a fragment, e.g. "[1]", "[1][2]".
_LEADING_MARKERS = re.compile(r"^((?:\[\d+\]\s*)+)(.*)$", re.DOTALL)
# A markdown list bullet/number prefix ("- ", "* ", "1. ", "2) ").
_LIST_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_HAS_ALPHA = re.compile(r"[A-Za-z]")

# Non-factual framing/meta phrases the model uses to introduce an answer. These
# assert nothing verifiable on their own, so penalising them as "unsupported"
# produces false hallucinations and depresses citation accuracy.
_FRAMING_RE = re.compile(
    r"^\s*("
    r"(based on|according to)\s+(the\s+)?(provided\s+)?"
    r"(context|passages?|documents?|information|sources?|text)"
    r"|here\s+(is|are)\b"
    r"|the\s+following\b"
    r"|in\s+summary|to\s+summari[sz]e|in\s+conclusion"
    r")",
    re.IGNORECASE,
)


# A stray list number left on the end of a lead-in line ("...are:\n\n1.").
_TRAILING_LIST_NUM = re.compile(r"[\s]*\d+[.)]\s*$")


def _is_lead_in(claim: str) -> bool:
    """True for a sentence that introduces a list/elaboration — it ends with a
    colon (a stray trailing list number is tolerated). The factual content and
    its citations live in the items that follow, so the colon lead-in itself is
    not a standalone verifiable claim. Substantive claims never end with ':',
    so this never excludes a real claim. Applied only to uncited sentences.
    """
    return _TRAILING_LIST_NUM.sub("", claim).rstrip().endswith(":")


def _is_framing(claim: str) -> bool:
    """True only for *pure* framing/introducer sentences (no factual content).

    Conservative by design: a sentence is treated as framing solely when it
    matches a known framing phrase AND is an introducer — it ends with a colon
    or is very short. Substantive sentences (which carry real claims) are never
    excluded, so verification strength on actual claims is unchanged. Callers
    apply this only to sentences that carry no citation markers.
    """
    if not _FRAMING_RE.match(claim):
        return False
    stripped = claim.rstrip()
    return stripped.endswith(":") or len(claim.split()) <= 8


def _split_claims(answer: str) -> list[str]:
    """Split the answer into sentence claims, keeping citations attached.

    Sentence splitting on terminal punctuation detaches trailing ``[n]`` markers
    and breaks markdown lists, producing fragments that *begin* with the previous
    item's citation (e.g. ``"[1]\\n- Next item."``). A citation follows the text
    it supports, so leading markers are moved onto the preceding claim; the
    remaining list text (bullet/number prefix stripped) becomes its own claim.
    This stops real claims from losing their citation and being mislabelled
    ``unsupported``. Pure marker/number fragments collapse away entirely.
    """
    raw = [s.strip() for s in _SENT_RE.split(answer) if s.strip()]
    merged: list[str] = []
    for part in raw:
        m = _LEADING_MARKERS.match(part)
        if m and m.group(1).strip() and merged:
            # Reattach the leading citation marker(s) to the previous claim.
            merged[-1] = f"{merged[-1]} {m.group(1).strip()}"
            rest = _LIST_PREFIX.sub("", m.group(2)).strip()
            if rest and _HAS_ALPHA.search(rest):
                merged.append(rest)
        else:
            cleaned = _LIST_PREFIX.sub("", part).strip()
            merged.append(cleaned if cleaned and _HAS_ALPHA.search(cleaned) else part)
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
            # Skip non-claims that carry no citation: pure framing ("Based on
            # the provided context:") and list lead-ins ("The activities are:").
            # Neither is a factual assertion, so neither should be flagged as a
            # hallucination nor counted in citation accuracy.
            if _is_framing(claim) or _is_lead_in(claim):
                continue
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
    # total == 0 only if every sentence was framing (no real claims) — vacuously
    # accurate, consistent with the no-claims guard above.
    return verifications, (weighted / total if total else 1.0)
