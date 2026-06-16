"""Chunker factory — maps strategy strings to concrete chunker instances."""
from __future__ import annotations

from app.chunking.base import BaseChunker, ChunkPiece

__all__ = ["get_chunker", "BaseChunker", "ChunkPiece"]


def get_chunker(strategy: str) -> BaseChunker:
    """Return the appropriate chunker for *strategy*.

    Supported: fixed | recursive | semantic
    Raises ValueError for unknown strategies.
    """
    if strategy == "fixed":
        from app.chunking.fixed import FixedChunker
        return FixedChunker()
    elif strategy == "recursive":
        from app.chunking.recursive import RecursiveChunker
        return RecursiveChunker()
    elif strategy == "semantic":
        from app.chunking.semantic import SemanticChunker
        return SemanticChunker()
    else:
        raise ValueError(f"Unsupported chunking strategy: {strategy!r}")
