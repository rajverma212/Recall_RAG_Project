"""Embedding client — thin adapter over the embedding provider layer.

Kept as a stable façade so retrieval / ingestion / dedup / semantic chunking
continue to import ``get_embedding_client()`` unchanged while the actual backend
(OpenAI / BGE / Voyage / Local) is selected by ``EMBEDDING_PROVIDER``.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.providers.embeddings.factory import get_embedding_provider

logger = get_logger(__name__)


class EmbeddingResult:
    def __init__(self, vectors: list[list[float]], tokens: int, price_per_1m: float):
        self.vectors = vectors
        self.tokens = tokens
        self._price_per_1m = price_per_1m

    @property
    def cost_usd(self) -> float:
        return self.tokens / 1_000_000 * self._price_per_1m


class EmbeddingClient:
    """Backward-compatible wrapper delegating to the active embedding provider."""

    def embed(self, texts: list[str]) -> EmbeddingResult:
        provider = get_embedding_provider()
        batch = provider.embed(texts)
        return EmbeddingResult(batch.vectors, batch.tokens, provider.price_per_1m)

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text]).vectors[0]


_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
