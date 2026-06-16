"""System & observability endpoints: /v1/health, /v1/metrics, /v1/providers."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import metrics
from app.db.session import get_db
from app.models.query_log import QueryLog

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Liveness + dependency reachability (best-effort, never raises)."""
    deps = {"postgres": False, "qdrant": False}
    try:
        db.execute(text("SELECT 1"))
        deps["postgres"] = True
    except Exception:
        pass
    try:
        from app.services.vector_store import get_vector_store

        deps["qdrant"] = get_vector_store()._client is not None
    except Exception:
        pass
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "dependencies": deps,
    }


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)) -> dict:
    """Per-stage latency telemetry + query-log rollups."""
    snap = metrics.snapshot()
    query_stats = {"total_queries": 0, "avg_latency_ms": 0.0, "low_confidence_rate": 0.0}
    try:
        rows = db.execute(
            select(
                func.count(QueryLog.id),
                func.avg(QueryLog.latency_ms),
                func.avg(QueryLog.confidence),
            )
        ).one()
        n = rows[0] or 0
        low = 0
        if n:
            low = db.execute(
                select(func.count(QueryLog.id)).where(
                    QueryLog.confidence < settings.min_confidence_to_answer
                )
            ).scalar_one()
        query_stats = {
            "total_queries": n,
            "avg_latency_ms": round(float(rows[1] or 0), 1),
            "avg_confidence": round(float(rows[2] or 0), 2),
            "low_confidence_rate": round(low / n, 3) if n else 0.0,
        }
    except Exception:
        pass
    return {**snap, "queries": query_stats}


@router.get("/providers")
def providers() -> dict:
    """Report active + available LLM and embedding providers (no secrets)."""
    from app.providers.embeddings.factory import get_embedding_provider
    from app.providers.factory import get_llm_provider

    llm = get_llm_provider()
    emb = get_embedding_provider()
    return {
        "llm": {
            "configured": settings.llm_provider,
            "active": llm.name,
            "model": llm.model,
            "input_price_per_1m": llm.input_price_per_1m,
            "output_price_per_1m": llm.output_price_per_1m,
            "available": ["anthropic", "openai", "local"],
            "keys_present": {
                "anthropic": bool(settings.anthropic_api_key),
                "openai": bool(settings.openai_api_key),
            },
        },
        "embedding": {
            "configured": settings.embedding_provider,
            "active": emb.name,
            "model": emb.model,
            "dim": emb.dim,
            "available": ["openai", "bge", "voyage", "local"],
        },
    }
