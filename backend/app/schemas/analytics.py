"""Schemas for analytics, evaluations, and experiments endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    total_queries: int
    avg_confidence: float
    avg_citation_accuracy: float
    avg_latency_ms: float
    total_cost_usd: float
    queries_by_day: list[dict] = Field(default_factory=list)
    confidence_histogram: list[dict] = Field(default_factory=list)
    low_confidence_rate: float = 0.0  # share of answers below threshold


class EvaluationRunOut(BaseModel):
    id: str
    name: str
    dataset: str
    config: dict = Field(default_factory=dict)
    retrieval_recall: float | None = None
    answer_correctness: float | None = None
    faithfulness: float | None = None
    citation_accuracy: float | None = None
    confidence_calibration: float | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ExperimentOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    config: dict = Field(default_factory=dict)
    evaluation_run_id: str | None = None
    metrics: dict = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True
