"""Startup validation — fail fast on misconfiguration, stay frictionless offline.

Two checks run during the FastAPI lifespan (see ``app.main``):

1. **Provider validation** — if a *cloud* LLM/embedding provider is configured
   but unavailable (missing key / SDK), the factory silently falls back to the
   deterministic local provider. That is the right behaviour for tests, CI, and
   offline demos, but in ``ENVIRONMENT=production`` a silent downgrade to
   extractive heuristics is dangerous. There we raise.

2. **Embedding-dimension guardrail** — the active embedding model's output
   dimension must equal ``EMBEDDING_DIM`` (used to create the Qdrant collection)
   *and* the dimension of any pre-existing Qdrant collection. A mismatch makes
   vector search silently wrong or makes upserts fail at request time with an
   opaque error. This always raises (it is a genuine bug, never a downgrade),
   but does not trigger for the local provider where the dims line up by
   construction — so the offline test path is unaffected.

The module is import-light and never makes a paid network call.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class StartupValidationError(RuntimeError):
    """Raised when a fatal misconfiguration is detected at boot."""


@dataclass
class ProviderStatus:
    kind: str  # "llm" | "embedding"
    configured: str  # the requested provider name
    active: str  # the provider actually in use after fallback resolution
    healthy: bool  # configured provider is the active one (no silent downgrade)
    detail: str = ""


@dataclass
class StartupReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    providers: list[ProviderStatus] = field(default_factory=list)
    embedding_dim_expected: int | None = None
    embedding_dim_collection: int | None = None


def _provider_status() -> list[ProviderStatus]:
    """Resolve active providers and report whether a silent fallback occurred."""
    from app.providers.embeddings.factory import get_embedding_provider
    from app.providers.factory import get_llm_provider

    statuses: list[ProviderStatus] = []

    llm = get_llm_provider()
    llm_healthy = llm.name == settings.llm_provider
    statuses.append(
        ProviderStatus(
            kind="llm",
            configured=settings.llm_provider,
            active=llm.name,
            healthy=llm_healthy,
            detail=(
                "active provider matches configuration"
                if llm_healthy
                else f"configured '{settings.llm_provider}' unavailable; "
                f"using '{llm.name}' fallback (check API key / SDK install)"
            ),
        )
    )

    emb = get_embedding_provider()
    emb_healthy = emb.name == settings.embedding_provider
    statuses.append(
        ProviderStatus(
            kind="embedding",
            configured=settings.embedding_provider,
            active=emb.name,
            healthy=emb_healthy,
            detail=(
                "active provider matches configuration"
                if emb_healthy
                else f"configured '{settings.embedding_provider}' unavailable; "
                f"using '{emb.name}' fallback (check API key / SDK install)"
            ),
        )
    )
    return statuses


def validate_embedding_dimensions(report: StartupReport) -> None:
    """Verify active-model dim == EMBEDDING_DIM == existing Qdrant collection dim."""
    from app.providers.embeddings.factory import get_embedding_provider
    from app.services.vector_store import get_vector_store

    provider = get_embedding_provider()
    expected = provider.dim or settings.embedding_dim
    report.embedding_dim_expected = expected

    # 1. Model output dim vs configured EMBEDDING_DIM (what the collection is built with).
    if provider.dim and provider.dim != settings.embedding_dim:
        report.ok = False
        report.errors.append(
            f"Embedding dimension mismatch: active provider "
            f"'{provider.name}' ({provider.model}) produces {provider.dim}-dim "
            f"vectors, but EMBEDDING_DIM={settings.embedding_dim}. "
            f"Set EMBEDDING_DIM={provider.dim} in your environment and re-ingest."
        )

    # 2. Configured/active dim vs an existing Qdrant collection.
    collection_dim = get_vector_store().collection_dim()
    report.embedding_dim_collection = collection_dim
    if collection_dim is not None and collection_dim != expected:
        report.ok = False
        report.errors.append(
            f"Embedding dimension mismatch: Qdrant collection "
            f"'{settings.qdrant_collection}' was created with {collection_dim}-dim "
            f"vectors, but the active embedding provider '{provider.name}' "
            f"produces {expected}-dim vectors. Either switch EMBEDDING_PROVIDER/"
            f"EMBEDDING_DIM back to the {collection_dim}-dim model, or drop and "
            f"re-create the collection (delete it in Qdrant, then re-ingest)."
        )


def run_startup_checks(*, strict: bool | None = None) -> StartupReport:
    """Run all boot-time validations.

    Args:
        strict: When True, a silent cloud→local provider downgrade is fatal.
            Defaults to ``True`` only in ``ENVIRONMENT=production`` so local/CI
            keep their frictionless offline fallback.

    Returns:
        StartupReport. Callers decide whether to abort on ``not report.ok``.
    """
    if strict is None:
        strict = settings.environment == "production"

    report = StartupReport()
    report.providers = _provider_status()

    for ps in report.providers:
        if not ps.healthy:
            msg = f"[{ps.kind}] {ps.detail}"
            if strict:
                report.ok = False
                report.errors.append(msg)
            else:
                report.warnings.append(msg)

    # Embedding-dim mismatch is a genuine bug, fatal regardless of environment.
    validate_embedding_dimensions(report)

    for w in report.warnings:
        logger.warning(f"startup: {w}")
    for e in report.errors:
        logger.error(f"startup: {e}")
    if report.ok and not report.warnings:
        logger.info("startup: all provider/embedding checks passed")

    return report
