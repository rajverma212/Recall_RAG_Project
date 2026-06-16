"""Deterministic offline embedding provider.

Hashes token buckets into a fixed-dim, L2-normalised vector. Not semantically
meaningful, but stable and unit-norm — enough to exercise the cosine-based
vector store and dedup paths without a key or network.
"""
from __future__ import annotations

import hashlib
import math

from app.core.config import settings
from app.providers.embeddings.base import BaseEmbeddingProvider, EmbeddingBatch


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    name = "local"
    model = "local-hash"
    price_per_1m = 0.0

    def __init__(self) -> None:
        self.dim = settings.embedding_dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        vectors = [self._embed_one(t) for t in texts]
        tokens = sum(len(t.split()) for t in texts)
        return EmbeddingBatch(vectors=vectors, tokens=tokens)
