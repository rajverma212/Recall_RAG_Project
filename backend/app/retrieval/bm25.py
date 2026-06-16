"""Sparse (BM25) retriever backed by rank-bm25.

The index is built lazily from all non-duplicate Chunk rows in Postgres.
The index + chunk list are cached in memory; a cheap row-count check triggers
a rebuild when new chunks have been ingested.

Falls back gracefully to an empty result set when the DB is unreachable
(offline / test mode with the in-memory vector store).
"""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.retrieval import RetrievedChunk

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)

_WORD_RE = re.compile(r"\b\w+\b")


def _tokenize(text: str) -> list[str]:
    """Lowercase word-boundary tokenisation."""
    return _WORD_RE.findall(text.lower())


class Bm25Retriever:
    """BM25Okapi index over non-duplicate chunks loaded from Postgres."""

    def __init__(self) -> None:
        self._index = None  # BM25Okapi instance
        self._chunk_meta: list[dict] = []  # parallel list of chunk metadata
        self._corpus_tokens: list[list[str]] = []  # parallel tokenised corpus
        self._cached_count: int = -1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def invalidate(self) -> None:
        """Force a full index rebuild on the next search call."""
        self._index = None
        self._chunk_meta = []
        self._corpus_tokens = []
        self._cached_count = -1
        logger.info("BM25 index invalidated")

    def search(
        self, db: "Session", query: str, top_k: int | None = None
    ) -> tuple[list[RetrievedChunk], int]:
        """
        Returns (chunks, elapsed_ms).
        top_k defaults to settings.sparse_top_k.
        """
        if top_k is None:
            top_k = settings.sparse_top_k

        t0 = time.perf_counter()
        self._maybe_rebuild(db)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        if self._index is None or not self._chunk_meta:
            logger.warning("BM25 index is empty – returning no sparse results")
            return [], elapsed_ms

        tokens = _tokenize(query)
        query_token_set = set(tokens)
        scores = self._index.get_scores(tokens)

        # Pair (original_index, score), sort descending, take top_k
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

        chunks: list[RetrievedChunk] = []
        for rank, (idx, score) in enumerate(ranked, start=1):
            meta = self._chunk_meta[idx]
            # On small corpora BM25Okapi's IDF can be <= 0 even for genuine
            # matches (a term present in most/all docs), so we cannot filter on
            # score. Instead skip only chunks that share NO query token at all —
            # true non-matches — and keep the BM25 *ranking* intact for RRF.
            if not (query_token_set & set(self._corpus_tokens[idx])):
                continue
            chunks.append(
                RetrievedChunk(
                    chunk_id=meta["chunk_id"],
                    document_id=meta["document_id"],
                    text=meta["text"],
                    score=float(score),
                    source_file=meta["source_file"],
                    page_number=meta.get("page_number"),
                    section_title=meta.get("section_title"),
                    heading_path=meta.get("heading_path"),
                    rank=rank,
                )
            )

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.debug(f"BM25 retrieval: {len(chunks)} hits in {elapsed_ms}ms")
        return chunks, elapsed_ms

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_rebuild(self, db: "Session") -> None:
        """Rebuild the index if the chunk count changed or index is missing."""
        try:
            current_count = self._get_chunk_count(db)
        except Exception as exc:
            logger.warning(f"BM25: cannot query Postgres, keeping stale index: {exc}")
            return

        if self._index is not None and current_count == self._cached_count:
            return  # cache is fresh

        logger.info(
            f"BM25: rebuilding index (prev_count={self._cached_count}, "
            f"new_count={current_count})"
        )
        self._build_index(db)
        self._cached_count = current_count

    def _get_chunk_count(self, db: "Session") -> int:
        from sqlalchemy import func, select

        from app.models.chunk import Chunk

        stmt = select(func.count()).select_from(Chunk).where(Chunk.is_duplicate == False)  # noqa: E712
        return db.execute(stmt).scalar_one()

    def _build_index(self, db: "Session") -> None:
        from sqlalchemy import select

        from app.models.chunk import Chunk

        stmt = select(Chunk).where(Chunk.is_duplicate == False)  # noqa: E712
        rows = db.execute(stmt).scalars().all()

        corpus_tokens: list[list[str]] = []
        meta_list: list[dict] = []
        for row in rows:
            corpus_tokens.append(_tokenize(row.text))
            meta_list.append(
                {
                    "chunk_id": row.id,
                    "document_id": row.document_id,
                    "text": row.text,
                    "source_file": row.source_file,
                    "page_number": row.page_number,
                    "section_title": row.section_title,
                    "heading_path": row.heading_path,
                }
            )

        if not corpus_tokens:
            logger.warning("BM25: no non-duplicate chunks found in DB")
            self._index = None
            self._chunk_meta = []
            self._corpus_tokens = []
            return

        try:
            from rank_bm25 import BM25Okapi

            self._index = BM25Okapi(corpus_tokens)
            self._chunk_meta = meta_list
            self._corpus_tokens = corpus_tokens
            logger.info(f"BM25: indexed {len(meta_list)} chunks")
        except Exception as exc:
            logger.error(f"BM25: failed to build index: {exc}")
            self._index = None
            self._chunk_meta = []
            self._corpus_tokens = []


# Module-level singleton
_bm25_retriever: Bm25Retriever | None = None


def get_bm25_retriever() -> Bm25Retriever:
    global _bm25_retriever
    if _bm25_retriever is None:
        _bm25_retriever = Bm25Retriever()
    return _bm25_retriever
