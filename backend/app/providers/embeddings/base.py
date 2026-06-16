"""Provider-agnostic embedding interface.

Retrieval, ingestion, dedup, and semantic chunking all embed text through a
``BaseEmbeddingProvider`` and never import a vendor SDK. Switching the embedding
backend is a one-line config change (``EMBEDDING_PROVIDER``).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingBatch:
    vectors: list[list[float]]
    tokens: int


class BaseEmbeddingProvider(ABC):
    name: str = "base"
    model: str = ""
    dim: int = 0
    price_per_1m: float = 0.0

    @abstractmethod
    def embed(self, texts: list[str]) -> EmbeddingBatch:
        """Embed a batch of texts. Vectors must be L2-normalised (cosine space)."""
