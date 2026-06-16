"""Voyage AI embedding provider (optional)."""
from __future__ import annotations

import math

from app.core.config import settings
from app.providers.embeddings.base import BaseEmbeddingProvider, EmbeddingBatch


def _normalise(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class VoyageEmbeddingProvider(BaseEmbeddingProvider):
    name = "voyage"

    def __init__(self) -> None:
        import voyageai

        self._client = voyageai.Client(api_key=settings.voyage_api_key)
        self.model = settings.voyage_embedding_model
        self.dim = settings.embedding_dim
        self.price_per_1m = 0.06  # approx voyage-3 pricing

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(vectors=[], tokens=0)
        result = self._client.embed(texts, model=self.model, input_type="document")
        vectors = [_normalise(v) for v in result.embeddings]
        tokens = getattr(result, "total_tokens", sum(len(t.split()) for t in texts))
        return EmbeddingBatch(vectors=vectors, tokens=tokens)
