"""Hybrid retrieval pipeline: dense → BM25 → RRF → rerank.

Each stage is timed and wrapped into a RetrievalStage for the inspector UI.
The pipeline returns the final top-k chunks plus the full RetrievalTrace.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.retrieval.bm25 import get_bm25_retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.reranker import get_reranker
from app.schemas.retrieval import RetrievalStage, RetrievalTrace, RetrievedChunk

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)


class HybridRetriever:
    """Orchestrates dense + sparse retrieval, RRF fusion, and reranking."""

    def __init__(self) -> None:
        self._dense = DenseRetriever()

    def retrieve(
        self, db: "Session", query: str
    ) -> tuple[list[RetrievedChunk], RetrievalTrace, int]:
        """Run the full pipeline.

        Returns:
            (final_chunks, trace, embedding_tokens)
            final_chunks: reranked top-k RetrievedChunk list
            trace:        RetrievalTrace (all four stages for the inspector)
            embedding_tokens: tokens consumed embedding the query
        """
        # ------------------------------------------------------------------ #
        # Stage 1: Dense                                                       #
        # ------------------------------------------------------------------ #
        t_dense = time.perf_counter()
        dense_chunks, embedding_tokens, _dense_ms = self._dense.search(
            query, top_k=settings.dense_top_k
        )
        dense_elapsed = int((time.perf_counter() - t_dense) * 1000)
        dense_stage = RetrievalStage(
            name="dense", results=dense_chunks, elapsed_ms=dense_elapsed
        )

        # ------------------------------------------------------------------ #
        # Stage 2: BM25                                                        #
        # ------------------------------------------------------------------ #
        t_bm25 = time.perf_counter()
        bm25_retriever = get_bm25_retriever()
        bm25_chunks, _bm25_ms = bm25_retriever.search(
            db, query, top_k=settings.sparse_top_k
        )
        bm25_elapsed = int((time.perf_counter() - t_bm25) * 1000)
        bm25_stage = RetrievalStage(
            name="bm25", results=bm25_chunks, elapsed_ms=bm25_elapsed
        )

        # ------------------------------------------------------------------ #
        # Stage 3: RRF fusion                                                  #
        # ------------------------------------------------------------------ #
        t_rrf = time.perf_counter()
        fused = reciprocal_rank_fusion(
            dense=dense_chunks,
            sparse=bm25_chunks,
            k=settings.rrf_k,
            dense_weight=settings.dense_weight,
            sparse_weight=settings.sparse_weight,
            top_k=settings.fusion_top_k,
        )
        rrf_elapsed = int((time.perf_counter() - t_rrf) * 1000)
        rrf_stage = RetrievalStage(
            name="rrf", results=fused, elapsed_ms=rrf_elapsed
        )

        # ------------------------------------------------------------------ #
        # Stage 4: Rerank                                                      #
        # ------------------------------------------------------------------ #
        t_rerank = time.perf_counter()
        reranker = get_reranker()
        reranked = reranker.rerank(
            query=query,
            candidates=fused,
            top_k=settings.rerank_top_k,
        )
        rerank_elapsed = int((time.perf_counter() - t_rerank) * 1000)
        reranked_stage = RetrievalStage(
            name="reranked", results=reranked, elapsed_ms=rerank_elapsed
        )

        trace = RetrievalTrace(
            dense=dense_stage,
            bm25=bm25_stage,
            rrf=rrf_stage,
            reranked=reranked_stage,
        )

        logger.info(
            f"Retrieval pipeline: dense={len(dense_chunks)} bm25={len(bm25_chunks)} "
            f"rrf={len(fused)} reranked={len(reranked)}"
        )
        return reranked, trace, embedding_tokens
