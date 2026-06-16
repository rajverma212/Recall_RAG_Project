"""OpenAI embedding client with batching, cost accounting, and a deterministic
offline fallback so the platform boots and the test-suite runs without a key.
"""
from __future__ import annotations

import hashlib
import math

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingResult:
    def __init__(self, vectors: list[list[float]], tokens: int):
        self.vectors = vectors
        self.tokens = tokens

    @property
    def cost_usd(self) -> float:
        return self.tokens / 1_000_000 * settings.embedding_price_per_1m


def _fake_embed(text: str) -> list[float]:
    """Deterministic pseudo-embedding for offline/dev/test use.

    Hashes token buckets into a fixed-dim vector and L2-normalises it. This is
    *not* semantically meaningful but is stable and unit-norm, which keeps the
    cosine-based dedup and vector store code exercisable without an API key.
    """
    dim = settings.embedding_dim
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class EmbeddingClient:
    def __init__(self) -> None:
        self._client = None
        if settings.openai_api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=settings.openai_api_key)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"OpenAI client init failed, using fallback: {exc}")

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult([], 0)
        if self._client is None:
            vectors = [_fake_embed(t) for t in texts]
            tokens = sum(len(t.split()) for t in texts)
            return EmbeddingResult(vectors, tokens)
        resp = self._client.embeddings.create(
            model=settings.embedding_model, input=texts
        )
        vectors = [d.embedding for d in resp.data]
        tokens = resp.usage.total_tokens
        return EmbeddingResult(vectors, tokens)

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text]).vectors[0]


_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
