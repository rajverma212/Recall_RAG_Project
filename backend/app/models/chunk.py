"""Chunk model — one row per processed text chunk.

The chunk text + metadata live in Postgres (source of truth); the embedding
vector lives in Qdrant keyed by this chunk's ``id``. BM25 indexes ``text``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )

    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)  # position in doc

    # ----- Provenance metadata -----
    source_file: Mapped[str] = mapped_column(String(512))
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(512))
    heading_path: Mapped[str | None] = mapped_column(Text)  # "H1 > H2 > H3"

    # ----- Chunking metadata -----
    strategy: Mapped[str] = mapped_column(String(32))
    chunk_size: Mapped[int] = mapped_column(Integer)
    chunk_overlap: Mapped[int] = mapped_column(Integer)

    # ----- Dedup -----
    is_duplicate: Mapped[bool] = mapped_column(default=False)
    duplicate_of: Mapped[str | None] = mapped_column(String(36))
    dedup_similarity: Mapped[float | None] = mapped_column(Float)

    embedded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")  # noqa: F821
