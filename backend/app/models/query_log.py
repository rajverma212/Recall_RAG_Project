"""QueryLog model — analytics, cost tracking, and audit for every /ask call."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)

    # Retrieval/citation telemetry persisted as JSON for the inspector UI.
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSON, default=list)
    citations: Mapped[list] = mapped_column(JSON, default=list)

    confidence: Mapped[float | None] = mapped_column(Float)
    citation_accuracy: Mapped[float | None] = mapped_column(Float)
    retrieval_confidence: Mapped[float | None] = mapped_column(Float)
    reranker_confidence: Mapped[float | None] = mapped_column(Float)

    prompt_version: Mapped[str | None] = mapped_column(String(32))
    experiment_id: Mapped[str | None] = mapped_column(String(36), index=True)

    # ----- Cost / latency -----
    embedding_tokens: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
