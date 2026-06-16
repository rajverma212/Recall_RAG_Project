"""OpenAI embedding provider (text-embedding-3-small by default)."""
from __future__ import annotations

import math

from app.core.config import settings
from app.providers.embeddings.base import BaseEmbeddingProvider, EmbeddingBatch


def _normalise(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.embedding_model
        self.dim = settings.embedding_dim
        self.price_per_1m = settings.embedding_price_per_1m

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(vectors=[], tokens=0)
        resp = self._client.embeddings.create(model=self.model, input=texts)
        vectors = [_normalise(d.embedding) for d in resp.data]
        return EmbeddingBatch(vectors=vectors, tokens=resp.usage.total_tokens)
