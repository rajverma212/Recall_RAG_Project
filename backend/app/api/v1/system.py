"""System & observability endpoints: /v1/health, /v1/metrics, /v1/providers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import metrics
from app.db.session import get_db
from app.models.query_log import QueryLog

router = APIRouter()


# --------------------------------------------------------------------------- #
# Health                                                                       #
# --------------------------------------------------------------------------- #


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict:
    """Liveness + readiness across every critical dependency.

    Verifies: database, vector store, active LLM provider, and the retrieval
    system. Best-effort and never raises, but returns HTTP 503 when any
    *required* dependency is down so load balancers / uptime checks can react.
    """
    checks: dict[str, dict] = {}

    # 1. Database
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "detail": str(exc)[:200]}

    # 2. Vector store
    try:
        from app.services.vector_store import get_vector_store

        vs = get_vector_store()
        backend = "qdrant" if vs._client is not None else "in_memory"
        checks["vector_store"] = {
            "ok": True,
            "backend": backend,
            "collection": settings.qdrant_collection,
            "vectors": vs.count(),
        }
    except Exception as exc:
        checks["vector_store"] = {"ok": False, "detail": str(exc)[:200]}

    # 3. Active LLM provider (no network call — reports resolved provider).
    try:
        from app.providers.factory import get_llm_provider

        llm = get_llm_provider()
        healthy = llm.name == settings.llm_provider
        checks["llm_provider"] = {
            "ok": healthy,
            "configured": settings.llm_provider,
            "active": llm.name,
            "model": llm.model,
        }
    except Exception as exc:
        checks["llm_provider"] = {"ok": False, "detail": str(exc)[:200]}

    # 4. Retrieval system (retriever + embedding provider construct cleanly).
    try:
        from app.providers.embeddings.factory import get_embedding_provider
        from app.retrieval.pipeline import HybridRetriever

        HybridRetriever()
        emb = get_embedding_provider()
        checks["retrieval"] = {"ok": True, "embedding_provider": emb.name}
    except Exception as exc:
        checks["retrieval"] = {"ok": False, "detail": str(exc)[:200]}

    # Required for readiness: database + vector store + retrieval. The LLM
    # provider being on its local fallback degrades quality but is still "up",
    # so it is reported but not required (matches the offline-first contract).
    required = ("database", "vector_store", "retrieval")
    overall_ok = all(checks[k]["ok"] for k in required)
    if not overall_ok:
        response.status_code = 503

    return {
        "status": "ok" if overall_ok else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "checks": checks,
    }


# --------------------------------------------------------------------------- #
# Metrics                                                                      #
# --------------------------------------------------------------------------- #


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)) -> dict:
    """Per-stage latency telemetry + business metrics.

    Business metrics (from the QueryLog table): total queries, average latency,
    success rate (answered above the confidence floor), and mean citation
    accuracy. Falls back to zeros when the DB is unavailable.
    """
    snap = metrics.snapshot()
    queries = {
        "total_queries": 0,
        "avg_latency_ms": 0.0,
        "success_rate": 0.0,
        "citation_accuracy": 0.0,
        "avg_confidence": 0.0,
        "low_confidence_rate": 0.0,
    }
    try:
        row = db.execute(
            select(
                func.count(QueryLog.id),
                func.avg(QueryLog.latency_ms),
                func.avg(QueryLog.confidence),
                func.avg(QueryLog.citation_accuracy),
            )
        ).one()
        n = row[0] or 0
        if n:
            answered = db.execute(
                select(func.count(QueryLog.id)).where(
                    QueryLog.confidence >= settings.min_confidence_to_answer
                )
            ).scalar_one()
            queries = {
                "total_queries": n,
                "avg_latency_ms": round(float(row[1] or 0), 1),
                "success_rate": round(answered / n, 3),
                "citation_accuracy": round(float(row[3] or 0), 3),
                "avg_confidence": round(float(row[2] or 0), 2),
                "low_confidence_rate": round((n - answered) / n, 3),
            }
    except Exception:
        pass
    return {**snap, "queries": queries}


# --------------------------------------------------------------------------- #
# Providers                                                                    #
# --------------------------------------------------------------------------- #


@router.get("/providers")
def providers() -> dict:
    """Report active + available LLM and embedding providers with status.

    Returns, per layer: the configured provider, the *active* provider (after
    fallback resolution), the list of available providers, and a status block
    indicating whether a silent downgrade occurred. No secrets are exposed.
    """
    from app.providers.embeddings.factory import get_embedding_provider
    from app.providers.factory import get_llm_provider

    llm = get_llm_provider()
    emb = get_embedding_provider()

    llm_healthy = llm.name == settings.llm_provider
    emb_healthy = emb.name == settings.embedding_provider

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
            "status": {
                "healthy": llm_healthy,
                "state": "active" if llm_healthy else "fallback",
                "detail": (
                    "configured provider is active"
                    if llm_healthy
                    else f"configured '{settings.llm_provider}' unavailable; "
                    f"serving from '{llm.name}' fallback"
                ),
            },
        },
        "embedding": {
            "configured": settings.embedding_provider,
            "active": emb.name,
            "model": emb.model,
            "dim": emb.dim,
            "available": ["openai", "bge", "voyage", "local"],
            "keys_present": {
                "openai": bool(settings.openai_api_key),
                "voyage": bool(settings.voyage_api_key),
            },
            "status": {
                "healthy": emb_healthy,
                "state": "active" if emb_healthy else "fallback",
                "detail": (
                    "configured provider is active"
                    if emb_healthy
                    else f"configured '{settings.embedding_provider}' unavailable; "
                    f"serving from '{emb.name}' fallback"
                ),
            },
        },
    }
