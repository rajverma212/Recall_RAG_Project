"""Schemas for the /v1/ask endpoint."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievalTrace


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    stream: bool = False
    include_trace: bool = True
    prompt_version: str | None = None
    experiment_id: str | None = None


class Citation(BaseModel):
    marker: int  # the [n] number in the answer
    chunk_id: str
    document_id: str
    source_file: str
    page_number: int | None = None
    section_title: str | None = None
    quote: str  # supporting span from the chunk
    text: str  # full chunk text


class ClaimVerification(BaseModel):
    claim: str
    cited_markers: list[int] = Field(default_factory=list)
    status: Literal["supported", "partially_supported", "unsupported"]
    rationale: str | None = None


class ConfidenceBreakdown(BaseModel):
    retrieval_confidence: float
    reranker_confidence: float
    citation_coverage: float
    citation_accuracy: float
    score: float = Field(..., ge=0, le=100)


class AskResponse(BaseModel):
    query_id: str
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    verifications: list[ClaimVerification] = Field(default_factory=list)
    confidence: ConfidenceBreakdown
    trace: RetrievalTrace | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    prompt_version: str | None = None
