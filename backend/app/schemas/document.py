"""Schemas for documents and ingestion."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    filename: str
    doc_type: str
    title: str | None = None
    num_pages: int | None = None
    num_chunks: int
    status: str
    chunking_strategy: str | None = None
    error: str | None = None
    ingested_at: datetime
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    num_chunks: int = 0
    num_duplicates_skipped: int = 0
    message: str | None = None
