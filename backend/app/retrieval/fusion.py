"""Reciprocal Rank Fusion (RRF) for combining dense and sparse results.

Formula per chunk:
    score = dense_weight * 1/(k + rank_dense)
          + sparse_weight * 1/(k + rank_sparse)

Only chunks that appear in at least one list receive a non-zero score.
Chunks absent from a list are given a rank of ∞ (contributing 0 from that list).
"""
from __future__ import annotations

from app.core.config import settings
from app.schemas.retrieval import RetrievedChunk


def reciprocal_rank_fusion(
    dense: list[RetrievedChunk],
    sparse: list[RetrievedChunk],
    k: int | None = None,
    dense_weight: float | None = None,
    sparse_weight: float | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Fuse dense + sparse result lists via RRF.

    Args:
        dense:         Dense retrieval results (ranked 1..n).
        sparse:        BM25 retrieval results (ranked 1..n).
        k:             RRF smoothing constant (default settings.rrf_k = 60).
        dense_weight:  Weight for dense contribution (default settings.dense_weight).
        sparse_weight: Weight for sparse contribution (default settings.sparse_weight).
        top_k:         How many fused results to return (default settings.fusion_top_k).

    Returns:
        Fused list[RetrievedChunk] sorted by descending fused score, with .rank
        and .score updated to the fused values.
    """
    if k is None:
        k = settings.rrf_k
    if dense_weight is None:
        dense_weight = settings.dense_weight
    if sparse_weight is None:
        sparse_weight = settings.sparse_weight
    if top_k is None:
        top_k = settings.fusion_top_k

    # Build rank lookup by chunk_id for each list
    dense_rank: dict[str, int] = {c.chunk_id: c.rank or (i + 1) for i, c in enumerate(dense)}
    sparse_rank: dict[str, int] = {c.chunk_id: c.rank or (i + 1) for i, c in enumerate(sparse)}

    # Collect all unique chunk_ids
    all_ids = set(dense_rank) | set(sparse_rank)

    # Chunk metadata lookup (dense takes precedence for shared fields)
    meta: dict[str, RetrievedChunk] = {}
    for c in sparse:
        meta[c.chunk_id] = c
    for c in dense:
        meta[c.chunk_id] = c  # dense wins on conflict

    # Compute fused scores
    fused_scores: dict[str, float] = {}
    for cid in all_ids:
        score = 0.0
        if cid in dense_rank:
            score += dense_weight * (1.0 / (k + dense_rank[cid]))
        if cid in sparse_rank:
            score += sparse_weight * (1.0 / (k + sparse_rank[cid]))
        fused_scores[cid] = score

    # Sort by descending fused score
    sorted_ids = sorted(fused_scores, key=lambda x: fused_scores[x], reverse=True)
    sorted_ids = sorted_ids[:top_k]

    result: list[RetrievedChunk] = []
    for rank, cid in enumerate(sorted_ids, start=1):
        orig = meta[cid]
        result.append(
            RetrievedChunk(
                chunk_id=orig.chunk_id,
                document_id=orig.document_id,
                text=orig.text,
                score=fused_scores[cid],
                source_file=orig.source_file,
                page_number=orig.page_number,
                section_title=orig.section_title,
                heading_path=orig.heading_path,
                rank=rank,
            )
        )

    return result
