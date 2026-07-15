"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.ratelimit import RateLimitMiddleware
from app.core.startup import StartupValidationError, run_startup_checks
from app.db.init_db import init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    try:
        init_db()
    except Exception as exc:  # pragma: no cover
        logger.warning(f"init_db skipped: {exc}")

    # Provider + embedding-dimension validation. Fatal misconfiguration aborts
    # boot in production; local/CI degrade gracefully (see app.core.startup).
    report = run_startup_checks()
    if not report.ok:
        raise StartupValidationError("; ".join(report.errors))

    logger.info(f"{settings.app_name} started ({settings.environment})")
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

# Per-IP rate limiting (see app.core.ratelimit): a global default cap on all
# routes, a stricter cap on the LLM-spend /ask endpoints, and /health exempt.
# Added before CORS so CORSMiddleware ends up outermost — browser preflight
# (OPTIONS) is answered by CORS and never consumes the rate-limit budget.
app.add_middleware(RateLimitMiddleware)

_origins = settings.allowed_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # The CORS spec forbids credentials alongside a wildcard origin; the SPA is
    # stateless (no cookies), so credentials are only enabled once origins are
    # pinned to explicit production hosts.
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health() -> dict:
    # Liveness probe (Railway healthcheck) — exempt from rate limiting.
    return {"status": "ok", "app": settings.app_name}
