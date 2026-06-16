"""Deduplication logic for chunks.

Detects near-duplicate chunks using cosine similarity against:
  1. Previously indexed vectors in the vector store (cross-document dedup)
  2. Other vectors within the current batch (within-batch dedup)

Vectors are assumed to be L2-normalised, so cosine similarity = dot product.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.services.vector_store import get_vector_store

logger = get_logger(__name__)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class Deduplicator:
    """Flags new chunks as duplicates if they are too similar to existing ones."""

    def __init__(
        self,
        threshold: float | None = None,
        enabled: bool | None = None,
    ):
        self.threshold = threshold if threshold is not None else settings.dedup_cosine_threshold
        self.enabled = enabled if enabled is not None else settings.dedup_enabled

    def check(
        self,
        chunk_ids: list[str],
        texts: list[str],
        vectors: list[list[float]],
    ) -> list[tuple[bool, str | None, float]]:
        """Check *vectors* for duplicates.

        Returns a list of (is_duplicate, duplicate_of_id_or_None, similarity)
        tuples — one per input chunk, in the same order.

        Deduplication is performed in two passes:
        1. Within-batch: for each chunk, check all previously processed chunks
           in the same batch.
        2. Cross-document: query the vector store for the nearest neighbour.
        """
        if not self.enabled:
            return [(False, None, 0.0)] * len(vectors)

        vs = get_vector_store()
        results: list[tuple[bool, str | None, float]] = []

        # In-batch vectors already accepted in this call (chunk_id -> vector)
        batch_accepted: dict[str, list[float]] = {}

        for i, (cid, text, vec) in enumerate(zip(chunk_ids, texts, vectors)):
            best_sim = 0.0
            best_id: str | None = None

            # 1. Within-batch similarity
            for prev_id, prev_vec in batch_accepted.items():
                sim = _dot(vec, prev_vec)
                if sim > best_sim:
                    best_sim = sim
                    best_id = prev_id

            # 2. Cross-document similarity via vector store
            hits = vs.search(vec, top_k=1)
            if hits:
                cross_sim = hits[0].score
                cross_id = hits[0].chunk_id
                if cross_sim > best_sim:
                    best_sim = cross_sim
                    best_id = cross_id

            is_dup = best_sim >= self.threshold

            if is_dup:
                logger.info(
                    f"Dedup: chunk {cid!r} is duplicate of {best_id!r} "
                    f"(similarity={best_sim:.4f} >= threshold={self.threshold})"
                )
                results.append((True, best_id, best_sim))
            else:
                # Accept this chunk for within-batch comparison
                batch_accepted[cid] = vec
                results.append((False, None, best_sim))

        return results
