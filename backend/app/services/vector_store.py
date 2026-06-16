"""Qdrant vector store wrapper.

Encapsulates collection lifecycle and dense search so the rest of the codebase
never imports the Qdrant client directly. Falls back to an in-memory store when
Qdrant is unreachable (keeps unit tests and local dev frictionless).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VectorHit:
    chunk_id: str
    score: float
    payload: dict


class _InMemoryStore:
    """Cosine-similarity fallback used when Qdrant is unavailable."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[list[float], dict]] = {}

    def upsert(self, ids, vectors, payloads):
        for i, v, p in zip(ids, vectors, payloads):
            self._data[i] = (v, p)

    def search(self, vector, top_k, doc_ids=None):
        def cos(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            return dot  # vectors are pre-normalised

        scored = [
            VectorHit(cid, cos(vector, v), p)
            for cid, (v, p) in self._data.items()
            if doc_ids is None or p.get("document_id") in doc_ids
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

    def delete_document(self, document_id):
        self._data = {
            k: v for k, v in self._data.items()
            if v[1].get("document_id") != document_id
        }

    def count(self):
        return len(self._data)


class VectorStore:
    def __init__(self) -> None:
        self._mem = _InMemoryStore()
        self._client = None
        self._init_qdrant()

    def _init_qdrant(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(
                host=settings.qdrant_host, port=settings.qdrant_port, timeout=5
            )
            existing = {c.name for c in self._client.get_collections().collections}
            if settings.qdrant_collection not in existing:
                self._client.create_collection(
                    collection_name=settings.qdrant_collection,
                    vectors_config=VectorParams(
                        size=settings.embedding_dim, distance=Distance.COSINE
                    ),
                )
            logger.info("Qdrant connected")
        except Exception as exc:
            logger.warning(f"Qdrant unavailable, using in-memory store: {exc}")
            self._client = None

    def upsert(self, ids, vectors, payloads) -> None:
        if self._client is None:
            self._mem.upsert(ids, vectors, payloads)
            return
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=_uuid_to_int(i), vector=v, payload={**p, "chunk_id": i})
            for i, v, p in zip(ids, vectors, payloads)
        ]
        self._client.upsert(settings.qdrant_collection, points=points)

    def search(self, vector, top_k, doc_ids=None) -> list[VectorHit]:
        if self._client is None:
            return self._mem.search(vector, top_k, doc_ids)
        hits = self._client.search(
            collection_name=settings.qdrant_collection,
            query_vector=vector,
            limit=top_k,
        )
        return [
            VectorHit(h.payload.get("chunk_id"), h.score, h.payload) for h in hits
        ]

    def delete_document(self, document_id: str) -> None:
        if self._client is None:
            self._mem.delete_document(document_id)
            return
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            MatchValue,
        )

        self._client.delete(
            settings.qdrant_collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id", match=MatchValue(value=document_id)
                        )
                    ]
                )
            ),
        )


def _uuid_to_int(u: str) -> int:
    return int(u.replace("-", "")[:16], 16)


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
