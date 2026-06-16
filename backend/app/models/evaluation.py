"""Evaluation models — runs and per-example results."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(256))
    dataset: Mapped[str] = mapped_column(String(256))

    # Snapshot of the config used, so runs are comparable/reproducible.
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Aggregate metrics.
    retrieval_recall: Mapped[float | None] = mapped_column(Float)
    answer_correctness: Mapped[float | None] = mapped_column(Float)
    faithfulness: Mapped[float | None] = mapped_column(Float)
    citation_accuracy: Mapped[float | None] = mapped_column(Float)
    confidence_calibration: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )

    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    example_id: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))  # direct|multi_hop|ambiguous|no_answer

    question: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str | None] = mapped_column(Text)
    predicted_answer: Mapped[str | None] = mapped_column(Text)

    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    passed: Mapped[bool] = mapped_column(default=False)

    run: Mapped["EvaluationRun"] = relationship(back_populates="results")
