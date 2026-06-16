"""Fixed-size token-window chunker with overlap."""
from __future__ import annotations

from app.chunking.base import BaseChunker, ChunkPiece, _count_tokens
from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.loaders.base import LoadedSection

logger = get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    """Split *text* into tokens. Uses tiktoken if available."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        token_ids = enc.encode(text)
        return [enc.decode([tid]) for tid in token_ids]
    except Exception:
        return text.split()


def _detokenize(tokens: list[str]) -> str:
    return "".join(tokens).strip()


class FixedChunker(BaseChunker):
    """Splits text into fixed-size token windows with overlap."""

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.chunk_size = chunk_size if chunk_size is not None else settings.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    def chunk(self, sections: list[LoadedSection]) -> list[ChunkPiece]:
        pieces: list[ChunkPiece] = []
        ordinal = 0

        for section in sections:
            text = section.text.strip()
            if not text:
                continue

            tokens = _tokenize(text)
            start = 0

            while start < len(tokens):
                end = min(start + self.chunk_size, len(tokens))
                window = tokens[start:end]
                chunk_text = _detokenize(window)

                if chunk_text:
                    pieces.append(
                        ChunkPiece(
                            text=chunk_text,
                            ordinal=ordinal,
                            token_count=len(window),
                            page_number=section.page_number,
                            section_title=section.section_title,
                            heading_path=section.heading_path,
                        )
                    )
                    ordinal += 1

                if end == len(tokens):
                    break
                start = end - self.chunk_overlap
                if start <= 0:
                    start = end  # prevent infinite loop on tiny texts

        logger.debug(f"FixedChunker: {len(sections)} sections → {len(pieces)} chunks")
        return pieces
