"""Tests for the system/observability endpoints: /health, /metrics, /providers.

Uses FastAPI's TestClient (which runs the lifespan, exercising startup
validation too). Fully offline: no Postgres/Qdrant/keys required. The database
check is expected to be down in this environment, so health reports "degraded"
(HTTP 503) while vector-store/retrieval checks pass — we assert structure and
the offline-first contract, not a live DB.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# /v1/health                                                                   #
# --------------------------------------------------------------------------- #


class TestHealth:
    def test_health_returns_all_checks(self, client):
        r = client.get("/v1/health")
        assert r.status_code in (200, 503)
        body = r.json()
        assert body["status"] in ("ok", "degraded")
        # All four dependency classes must be reported.
        for key in ("database", "vector_store", "llm_provider", "retrieval"):
            assert key in body["checks"]
            assert "ok" in body["checks"][key]

    def test_health_vector_store_and_retrieval_up_offline(self, client):
        """Vector store + retrieval must be healthy even with no external infra."""
        body = client.get("/v1/health").json()
        assert body["checks"]["vector_store"]["ok"] is True
        assert body["checks"]["retrieval"]["ok"] is True

    def test_health_503_when_required_dep_down(self, client):
        """With no Postgres in the test env, readiness must report 503/degraded."""
        r = client.get("/v1/health")
        if not r.json()["checks"]["database"]["ok"]:
            assert r.status_code == 503
            assert r.json()["status"] == "degraded"


# --------------------------------------------------------------------------- #
# /v1/metrics                                                                  #
# --------------------------------------------------------------------------- #


class TestMetrics:
    def test_metrics_exposes_business_fields(self, client):
        body = client.get("/v1/metrics").json()
        q = body["queries"]
        for field in (
            "total_queries",
            "avg_latency_ms",
            "success_rate",
            "citation_accuracy",
        ):
            assert field in q

    def test_metrics_has_stage_section(self, client):
        body = client.get("/v1/metrics").json()
        assert "stages" in body
        assert "uptime_seconds" in body


# --------------------------------------------------------------------------- #
# /v1/providers                                                                #
# --------------------------------------------------------------------------- #


class TestProviders:
    def test_providers_reports_llm_and_embedding(self, client):
        body = client.get("/v1/providers").json()
        assert "llm" in body and "embedding" in body

    def test_providers_status_block_present(self, client):
        body = client.get("/v1/providers").json()
        for layer in ("llm", "embedding"):
            assert "configured" in body[layer]
            assert "active" in body[layer]
            assert "available" in body[layer]
            assert "status" in body[layer]
            assert "healthy" in body[layer]["status"]
            assert body[layer]["status"]["state"] in ("active", "fallback")

    def test_providers_no_secrets_leaked(self, client):
        """Endpoint must report key *presence*, never key values."""
        import json

        raw = json.dumps(client.get("/v1/providers").json())
        assert "sk-" not in raw
        assert "keys_present" in raw
