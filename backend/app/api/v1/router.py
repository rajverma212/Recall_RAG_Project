"""Aggregates all v1 routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import analytics, ask, documents, evaluations, experiments

api_router = APIRouter()
api_router.include_router(ask.router, tags=["ask"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(evaluations.router, tags=["evaluations"])
api_router.include_router(analytics.router, tags=["analytics"])
api_router.include_router(experiments.router, tags=["experiments"])
