"""Dense (vector) retriever.

Embeds the query via the embedding client and searches the vector store.
Falls back to the in-memory store when Qdrant is unavailable.
"""
from __future__ import annotations

import time

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.retrieval import RetrievedChunk
from app.services.embeddings import get_embedding_client
from app.services.vector_store import get_vector_store

logger = get_logger(__name__)


class DenseRetriever:
    """Embed query → vector store search → list[RetrievedChunk]."""

    def search(
        self,
        query: str,
        top_k: int | None = None,
        doc_ids: list[str] | None = None,
    ) -> tuple[list[RetrievedChunk], int, float]:
        """
        Returns (chunks, embedding_tokens, elapsed_ms).
        top_k defaults to settings.dense_top_k.
        """
        if top_k is None:
            top_k = settings.dense_top_k

        t0 = time.perf_counter()
        client = get_embedding_client()
        result = client.embed([query])
        vector = result.vectors[0]
        embedding_tokens = result.tokens

        store = get_vector_store()
        hits = store.search(vector, top_k=top_k, doc_ids=doc_ids)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        chunks: list[RetrievedChunk] = []
        for rank, hit in enumerate(hits, start=1):
            payload = hit.payload or {}
            chunks.append(
                RetrievedChunk(
                    chunk_id=hit.chunk_id or "",
                    document_id=payload.get("document_id", ""),
                    text=payload.get("text", ""),
                    score=hit.score,
                    source_file=payload.get("source_file", ""),
                    page_number=payload.get("page_number"),
                    section_title=payload.get("section_title"),
                    heading_path=payload.get("heading_path"),
                    rank=rank,
                )
            )

        logger.debug(f"Dense retrieval: {len(chunks)} hits in {elapsed_ms}ms")
        return chunks, embedding_tokens, elapsed_ms
