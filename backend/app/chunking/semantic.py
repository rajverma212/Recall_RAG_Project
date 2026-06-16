"""Semantic chunker.

Splits sections into sentences, embeds them, computes cosine distance between
consecutive sentence embeddings, then starts a new chunk at breakpoints above
the settings.semantic_breakpoint_percentile percentile. Groups sentences into
chunks while respecting settings.chunk_size as a soft cap.
"""
from __future__ import annotations

import re

from app.chunking.base import BaseChunker, ChunkPiece, _count_tokens
from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.loaders.base import LoadedSection

logger = get_logger(__name__)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    sentences = _SENTENCE_SPLIT.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Return 1 - cosine_similarity for L2-normalised vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    # Vectors are pre-normalised (L2-norm = 1), so cosine_similarity = dot product
    return 1.0 - dot


def _percentile(values: list[float], p: float) -> float:
    """Return the p-th percentile of *values*."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (p / 100.0) * (len(sorted_vals) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_vals) - 1)
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


class SemanticChunker(BaseChunker):
    """Breakpoint-based semantic chunker using sentence embeddings."""

    def __init__(
        self,
        chunk_size: int | None = None,
        breakpoint_percentile: float | None = None,
    ):
        self.chunk_size = chunk_size if chunk_size is not None else settings.chunk_size
        self.breakpoint_percentile = (
            breakpoint_percentile
            if breakpoint_percentile is not None
            else settings.semantic_breakpoint_percentile
        )

    def chunk(self, sections: list[LoadedSection]) -> list[ChunkPiece]:
        from app.services.embeddings import get_embedding_client

        client = get_embedding_client()
        pieces: list[ChunkPiece] = []
        ordinal = 0

        for section in sections:
            text = section.text.strip()
            if not text:
                continue

            sentences = _split_sentences(text)
            if len(sentences) <= 1:
                # Can't find breakpoints — emit as a single chunk
                pieces.append(
                    ChunkPiece(
                        text=text,
                        ordinal=ordinal,
                        token_count=_count_tokens(text),
                        page_number=section.page_number,
                        section_title=section.section_title,
                        heading_path=section.heading_path,
                    )
                )
                ordinal += 1
                continue

            # Embed all sentences in one batch
            result = client.embed(sentences)
            vectors = result.vectors

            # Compute cosine distances between consecutive sentences
            distances = [
                _cosine_distance(vectors[i], vectors[i + 1])
                for i in range(len(vectors) - 1)
            ]

            threshold = _percentile(distances, self.breakpoint_percentile)

            # Group sentences into chunks at breakpoints
            current_sentences: list[str] = [sentences[0]]
            current_tokens = _count_tokens(sentences[0])

            for i, sent in enumerate(sentences[1:], start=1):
                dist_idx = i - 1  # distance between sentence i-1 and i
                sent_tokens = _count_tokens(sent)
                at_breakpoint = distances[dist_idx] >= threshold
                would_exceed = (current_tokens + sent_tokens) > self.chunk_size

                if at_breakpoint or would_exceed:
                    # Flush current group
                    chunk_text = " ".join(current_sentences).strip()
                    if chunk_text:
                        pieces.append(
                            ChunkPiece(
                                text=chunk_text,
                                ordinal=ordinal,
                                token_count=current_tokens,
                                page_number=section.page_number,
                                section_title=section.section_title,
                                heading_path=section.heading_path,
                            )
                        )
                        ordinal += 1
                    current_sentences = [sent]
                    current_tokens = sent_tokens
                else:
                    current_sentences.append(sent)
                    current_tokens += sent_tokens

            # Flush the last group
            if current_sentences:
                chunk_text = " ".join(current_sentences).strip()
                if chunk_text:
                    pieces.append(
                        ChunkPiece(
                            text=chunk_text,
                            ordinal=ordinal,
                            token_count=current_tokens,
                            page_number=section.page_number,
                            section_title=section.section_title,
                            heading_path=section.heading_path,
                        )
                    )
                    ordinal += 1

        logger.debug(f"SemanticChunker: {len(sections)} sections → {len(pieces)} chunks")
        return pieces
