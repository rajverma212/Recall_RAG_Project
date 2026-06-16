"""Citation extraction: parse [n] markers from the answer and map them to
the numbered context chunks.

The *quote* field is the best-matching sentence/span from the cited chunk,
found by Jaccard overlap between the answer sentence containing the marker
and the chunk text.
"""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.schemas.ask import Citation
from app.schemas.retrieval import RetrievedChunk

logger = get_logger(__name__)

_MARKER_RE = re.compile(r"\[(\d+)\]")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_ONLY_MARKERS = re.compile(r"^(\[\d+\]\s*)+$")


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries; merge trailing marker-only fragments
    back into the preceding sentence so that citations placed after a period
    (e.g. "…syntax. [1]") are correctly associated with their claim."""
    raw = [s.strip() for s in _SENT_RE.split(text) if s.strip()]
    merged: list[str] = []
    for part in raw:
        if _ONLY_MARKERS.match(part) and merged:
            merged[-1] = merged[-1] + " " + part
        else:
            merged.append(part)
    return merged


def _best_matching_span(answer_sentence: str, chunk_text: str) -> str:
    """Return the sentence from chunk_text that best overlaps answer_sentence.

    Falls back to the first 200 characters of the chunk if nothing matches.
    """
    q_words = set(answer_sentence.lower().split())
    sentences = _split_sentences(chunk_text)
    if not sentences:
        return chunk_text[:200]

    best_sentence = sentences[0]
    best_score = 0.0
    for sent in sentences:
        s_words = set(sent.lower().split())
        union = q_words | s_words
        if union:
            score = len(q_words & s_words) / len(union)
            if score > best_score:
                best_score = score
                best_sentence = sent

    return best_sentence


def extract_citations(
    answer: str,
    context_chunks: list[RetrievedChunk],
) -> list[Citation]:
    """Parse [n] markers from *answer* and build Citation objects.

    Args:
        answer:         The model-generated answer text (may contain [1], [2], …).
        context_chunks: The reranked chunks that were passed to the model as
                        numbered context (1-indexed, position = marker number).

    Returns:
        Deduplicated list of Citation objects, one per unique (marker, chunk)
        pair encountered in the answer.
    """
    # Split answer into sentences to find the containing sentence per marker
    answer_sentences = _split_sentences(answer)

    # Map each sentence to the markers it contains
    sentence_markers: list[tuple[str, list[int]]] = []
    for sent in answer_sentences:
        markers = [int(m) for m in _MARKER_RE.findall(sent)]
        sentence_markers.append((sent, markers))

    # Collect citations; avoid duplicates (same marker + chunk_id)
    seen: set[tuple[int, str]] = set()
    citations: list[Citation] = []

    for sent, markers in sentence_markers:
        for marker in markers:
            # Markers are 1-indexed; context_chunks is 0-indexed
            idx = marker - 1
            if idx < 0 or idx >= len(context_chunks):
                logger.debug(f"Marker [{marker}] out of range (have {len(context_chunks)} chunks)")
                continue

            chunk = context_chunks[idx]
            key = (marker, chunk.chunk_id)
            if key in seen:
                continue
            seen.add(key)

            quote = _best_matching_span(sent, chunk.text)

            citations.append(
                Citation(
                    marker=marker,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    source_file=chunk.source_file,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    quote=quote,
                    text=chunk.text,
                )
            )

    # Sort by marker number for deterministic output
    citations.sort(key=lambda c: c.marker)
    return citations
