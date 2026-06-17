"""GET /v1/analytics — query volume, confidence, cost, latency rollups."""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.query_log import QueryLog
from app.schemas.analytics import AnalyticsSummary

router = APIRouter()


@router.get("/analytics", response_model=AnalyticsSummary)
def analytics(db: Session = Depends(get_db)):
    logs = db.scalars(select(QueryLog)).all()
    n = len(logs)
    if n == 0:
        return AnalyticsSummary(
            total_queries=0,
            avg_confidence=0,
            avg_citation_accuracy=0,
            avg_latency_ms=0,
            total_cost_usd=0,
        )

    avg_conf = sum(x.confidence or 0 for x in logs) / n
    avg_cit = sum(x.citation_accuracy or 0 for x in logs) / n
    avg_lat = sum(x.latency_ms for x in logs) / n
    total_cost = sum(x.cost_usd for x in logs)

    by_day: dict[str, int] = defaultdict(int)
    for x in logs:
        by_day[x.created_at.date().isoformat()] += 1

    buckets = [0] * 10  # 0-10,10-20,...,90-100
    for x in logs:
        c = min(int((x.confidence or 0) // 10), 9)
        buckets[c] += 1
    histogram = [
        {"bucket": f"{i*10}-{i*10+10}", "count": c} for i, c in enumerate(buckets)
    ]

    low_conf = sum(1 for x in logs if (x.confidence or 0) < 20) / n

    return AnalyticsSummary(
        total_queries=n,
        avg_confidence=round(avg_conf, 2),
        avg_citation_accuracy=round(avg_cit, 2),
        avg_latency_ms=round(avg_lat, 1),
        total_cost_usd=round(total_cost, 6),
        queries_by_day=[{"date": d, "count": c} for d, c in sorted(by_day.items())],
        confidence_histogram=histogram,
        low_confidence_rate=round(low_conf, 3),
    )
