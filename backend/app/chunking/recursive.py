"""Recursive character/token splitter (LangChain-style, no LangChain dependency).

Tries to split on a hierarchy of separators to keep chunks under chunk_size
tokens. Falls back to the next separator if a piece is still too large.
Applies chunk_overlap tokens of overlap between consecutive pieces.
"""
from __future__ import annotations

from app.chunking.base import BaseChunker, ChunkPiece, _count_tokens
from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.loaders.base import LoadedSection

logger = get_logger(__name__)

_DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_text_recursive(
    text: str,
    separators: list[str],
    chunk_size: int,
) -> list[str]:
    """Recursively split *text* on *separators* until every piece fits in *chunk_size* tokens."""
    if _count_tokens(text) <= chunk_size:
        return [text]

    if not separators:
        # Hard split by characters when nothing else works
        chars_per_token = max(1, len(text) // max(1, _count_tokens(text)))
        max_chars = chunk_size * chars_per_token
        return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

    sep = separators[0]
    rest = separators[1:]

    if sep == "":
        # Character-level split
        return _split_text_recursive(text, rest, chunk_size)

    parts = text.split(sep)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for part in parts:
        part_tokens = _count_tokens(part)

        if part_tokens > chunk_size:
            # This part is too large on its own — recurse on it
            if current:
                chunks.append(sep.join(current))
                current = []
                current_tokens = 0
            sub_chunks = _split_text_recursive(part, rest, chunk_size)
            chunks.extend(sub_chunks)
        elif current_tokens + part_tokens + (1 if current else 0) > chunk_size:
            # Flush current buffer
            if current:
                chunks.append(sep.join(current))
            current = [part]
            current_tokens = part_tokens
        else:
            current.append(part)
            current_tokens += part_tokens

    if current:
        chunks.append(sep.join(current))

    return [c for c in chunks if c.strip()]


def _add_overlap(chunks: list[str], overlap: int) -> list[str]:
    """Prepend up to *overlap* tokens from the previous chunk to each chunk."""
    if overlap <= 0 or len(chunks) < 2:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        prev_words = prev.split()
        overlap_text = " ".join(prev_words[-overlap:]) if len(prev_words) > overlap else prev
        merged = overlap_text + " " + chunks[i]
        result.append(merged.strip())

    return result


class RecursiveChunker(BaseChunker):
    """Recursive text splitter that preserves natural boundaries."""

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size if chunk_size is not None else settings.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap
        self.separators = separators if separators is not None else _DEFAULT_SEPARATORS

    def chunk(self, sections: list[LoadedSection]) -> list[ChunkPiece]:
        pieces: list[ChunkPiece] = []
        ordinal = 0

        for section in sections:
            text = section.text.strip()
            if not text:
                continue

            raw_chunks = _split_text_recursive(text, self.separators, self.chunk_size)
            raw_chunks = _add_overlap(raw_chunks, self.chunk_overlap)

            for chunk_text in raw_chunks:
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue
                pieces.append(
                    ChunkPiece(
                        text=chunk_text,
                        ordinal=ordinal,
                        token_count=_count_tokens(chunk_text),
                        page_number=section.page_number,
                        section_title=section.section_title,
                        heading_path=section.heading_path,
                    )
                )
                ordinal += 1

        logger.debug(f"RecursiveChunker: {len(sections)} sections → {len(pieces)} chunks")
        return pieces
