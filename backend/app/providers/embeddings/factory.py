"""Embedding provider factory with offline fallback (mirrors the LLM factory)."""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.embeddings.base import BaseEmbeddingProvider
from app.providers.embeddings.local_embeddings import LocalEmbeddingProvider

logger = get_logger(__name__)

_provider: BaseEmbeddingProvider | None = None


def _build(name: str) -> BaseEmbeddingProvider:
    if name == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        from app.providers.embeddings.openai_embeddings import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider()
    if name == "bge":
        from app.providers.embeddings.bge_embeddings import BgeEmbeddingProvider

        return BgeEmbeddingProvider()
    if name == "voyage":
        if not settings.voyage_api_key:
            raise RuntimeError("VOYAGE_API_KEY not set")
        from app.providers.embeddings.voyage_embeddings import VoyageEmbeddingProvider

        return VoyageEmbeddingProvider()
    if name == "local":
        return LocalEmbeddingProvider()
    raise RuntimeError(f"Unknown embedding provider: {name}")


def get_embedding_provider() -> BaseEmbeddingProvider:
    global _provider
    if _provider is None:
        try:
            _provider = _build(settings.embedding_provider)
            logger.info(f"Embedding provider: {_provider.name} ({_provider.model})")
        except Exception as exc:
            logger.warning(
                f"Embedding provider '{settings.embedding_provider}' unavailable "
                f"({exc}); falling back to LocalEmbeddingProvider"
            )
            _provider = LocalEmbeddingProvider()
    return _provider


def reset_embedding_provider() -> None:
    global _provider
    _provider = None
