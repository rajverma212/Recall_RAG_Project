"""Local BGE embedding provider (sentence-transformers, no API key required).

Runs ``BAAI/bge-small-en-v1.5`` (384-dim) on CPU/GPU. When selected, set
``EMBEDDING_DIM=384`` so the Qdrant collection matches the model output.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.embeddings.base import BaseEmbeddingProvider, EmbeddingBatch

logger = get_logger(__name__)


class BgeEmbeddingProvider(BaseEmbeddingProvider):
    name = "bge"
    price_per_1m = 0.0  # local inference, no per-token cost

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = settings.bge_embedding_model
        self._model = SentenceTransformer(self.model, device=settings.reranker_device)
        self.dim = self._model.get_sentence_embedding_dimension()
        if self.dim != settings.embedding_dim:
            logger.warning(
                f"BGE model dim {self.dim} != EMBEDDING_DIM {settings.embedding_dim}; "
                "set EMBEDDING_DIM to match before ingesting."
            )

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(vectors=[], tokens=0)
        # normalize_embeddings → unit vectors for cosine search.
        vecs = self._model.encode(texts, normalize_embeddings=True)
        vectors = [v.tolist() for v in vecs]
        tokens = sum(len(t.split()) for t in texts)
        return EmbeddingBatch(vectors=vectors, tokens=tokens)
