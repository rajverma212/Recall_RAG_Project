"""Schemas for retrieval results and the inspector view."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    source_file: str
    page_number: int | None = None
    section_title: str | None = None
    heading_path: str | None = None
    rank: int | None = None


class RetrievalStage(BaseModel):
    """One stage of the hybrid pipeline, for the Retrieval Inspector UI."""

    name: str  # "dense" | "bm25" | "rrf" | "reranked"
    results: list[RetrievedChunk] = Field(default_factory=list)
    elapsed_ms: int = 0


class RetrievalTrace(BaseModel):
    dense: RetrievalStage
    bm25: RetrievalStage
    rrf: RetrievalStage
    reranked: RetrievalStage
