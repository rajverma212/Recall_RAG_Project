"""Base chunker contract and ChunkPiece dataclass."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.ingestion.loaders.base import LoadedSection


def _count_tokens(text: str) -> int:
    """Return the token count for *text*.

    Tries tiktoken first; falls back to whitespace-split word count.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


@dataclass
class ChunkPiece:
    """A single chunk of text with provenance metadata."""

    text: str
    ordinal: int = 0
    token_count: int = 0

    # Provenance from the source LoadedSection
    page_number: int | None = None
    section_title: str | None = None
    heading_path: str | None = None

    def __post_init__(self):
        if self.token_count == 0 and self.text:
            self.token_count = _count_tokens(self.text)


class BaseChunker(ABC):
    """Abstract base class for text chunkers."""

    @abstractmethod
    def chunk(self, sections: list[LoadedSection]) -> list[ChunkPiece]:
        """Split *sections* into a flat list of ChunkPiece objects."""
        ...
