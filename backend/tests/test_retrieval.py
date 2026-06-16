"""Tests for the retrieval pipeline (dense, BM25, RRF, rerank).

All tests run fully offline: they seed the in-memory vector store directly
and mock the DB session so Postgres is never required.
"""
from __future__ import annotations

import sys
import os

# Ensure 'app' is importable from the backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import re
import uuid
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers to seed the in-memory vector store
# ---------------------------------------------------------------------------

def _fake_embed(text: str) -> list[float]:
    """Mirror the deterministic embedding used in embeddings.py."""
    import hashlib
    from app.core.config import settings
    dim = settings.embedding_dim
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _seed_vector_store(chunks: list[dict]) -> None:
    """Insert chunks into the singleton in-memory vector store."""
    from app.services.vector_store import get_vector_store
    store = get_vector_store()
    ids = [c["chunk_id"] for c in chunks]
    vectors = [_fake_embed(c["text"]) for c in chunks]
    payloads = [
        {
            "document_id": c.get("document_id", "doc-1"),
            "text": c["text"],
            "source_file": c.get("source_file", "test.pdf"),
            "page_number": c.get("page_number", 1),
            "section_title": c.get("section_title"),
            "heading_path": c.get("heading_path"),
        }
        for c in chunks
    ]
    store.upsert(ids, vectors, payloads)


# ---------------------------------------------------------------------------
# Sample chunks
# ---------------------------------------------------------------------------

CHUNKS = [
    {
        "chunk_id": "c1",
        "document_id": "doc-1",
        "text": "Python is a high-level programming language known for its simplicity.",
        "source_file": "python_intro.pdf",
        "page_number": 1,
        "section_title": "Intro",
    },
    {
        "chunk_id": "c2",
        "document_id": "doc-1",
        "text": "Machine learning uses algorithms to learn from data and make predictions.",
        "source_file": "ml_basics.pdf",
        "page_number": 2,
        "section_title": "ML",
    },
    {
        "chunk_id": "c3",
        "document_id": "doc-2",
        "text": "FastAPI is a modern web framework for building APIs with Python.",
        "source_file": "fastapi.pdf",
        "page_number": 3,
        "section_title": "FastAPI",
    },
    {
        "chunk_id": "c4",
        "document_id": "doc-2",
        "text": "Neural networks are a subset of machine learning inspired by the brain.",
        "source_file": "ml_basics.pdf",
        "page_number": 4,
        "section_title": "Neural",
    },
    {
        "chunk_id": "c5",
        "document_id": "doc-3",
        "text": "Docker containers package applications with their dependencies for deployment.",
        "source_file": "devops.pdf",
        "page_number": 5,
        "section_title": "Docker",
    },
]


@pytest.fixture(autouse=True)
def seed_store():
    """Seed the in-memory vector store before each test."""
    _seed_vector_store(CHUNKS)
    yield


# ---------------------------------------------------------------------------
# Mock DB session that returns our CHUNKS for BM25
# ---------------------------------------------------------------------------

class _FakeChunk:
    """Mimics the ORM Chunk model with just the fields BM25 needs."""
    def __init__(self, data: dict) -> None:
        self.id = data["chunk_id"]
        self.document_id = data.get("document_id", "doc-1")
        self.text = data["text"]
        self.source_file = data.get("source_file", "test.pdf")
        self.page_number = data.get("page_number", 1)
        self.section_title = data.get("section_title")
        self.heading_path = data.get("heading_path")
        self.is_duplicate = False


def _make_mock_db(chunks=None):
    """Return a mock Session that satisfies the BM25 retriever's queries."""
    if chunks is None:
        chunks = CHUNKS

    fake_rows = [_FakeChunk(c) for c in chunks]

    mock_db = MagicMock()

    # Smart result handles all query patterns:
    #   .scalar_one()         → count of rows (int)
    #   .scalars().all()      → list of chunk rows
    #   .scalar_one_or_none() → None
    class _SmartResult:
        def scalar_one(self):
            return len(fake_rows)

        def scalar_one_or_none(self):
            return None

        def scalars(self):
            class _Scalars:
                def all(self):
                    return fake_rows
            return _Scalars()

    mock_db.execute.return_value = _SmartResult()
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.rollback = MagicMock()
    return mock_db


# ---------------------------------------------------------------------------
# Dense retriever tests
# ---------------------------------------------------------------------------

class TestDenseRetriever:
    def test_returns_retrieved_chunks(self):
        from app.retrieval.dense import DenseRetriever
        from app.schemas.retrieval import RetrievedChunk

        dr = DenseRetriever()
        chunks, tokens, elapsed = dr.search("Python programming language", top_k=3)

        assert isinstance(chunks, list)
        assert len(chunks) <= 3
        assert all(isinstance(c, RetrievedChunk) for c in chunks)

    def test_ranks_are_assigned(self):
        from app.retrieval.dense import DenseRetriever

        dr = DenseRetriever()
        chunks, _, _ = dr.search("Python programming language", top_k=5)

        ranks = [c.rank for c in chunks]
        assert ranks == list(range(1, len(chunks) + 1))

    def test_scores_descending(self):
        from app.retrieval.dense import DenseRetriever

        dr = DenseRetriever()
        chunks, _, _ = dr.search("machine learning data", top_k=5)

        scores = [c.score for c in chunks]
        assert scores == sorted(scores, reverse=True)

    def test_returns_embedding_tokens(self):
        from app.retrieval.dense import DenseRetriever

        dr = DenseRetriever()
        _, tokens, _ = dr.search("test query")
        assert isinstance(tokens, int)
        assert tokens >= 0


# ---------------------------------------------------------------------------
# BM25 retriever tests
# ---------------------------------------------------------------------------

class TestBm25Retriever:
    def test_basic_search(self):
        from app.retrieval.bm25 import Bm25Retriever
        from app.schemas.retrieval import RetrievedChunk

        retriever = Bm25Retriever()
        db = _make_mock_db()
        chunks, elapsed = retriever.search(db, "Python programming", top_k=3)

        assert isinstance(chunks, list)
        assert all(isinstance(c, RetrievedChunk) for c in chunks)

    def test_relevant_chunks_ranked_higher(self):
        from app.retrieval.bm25 import Bm25Retriever

        retriever = Bm25Retriever()
        db = _make_mock_db()
        chunks, _ = retriever.search(db, "machine learning algorithms", top_k=5)

        # At least one of the ML chunks should appear
        chunk_ids = [c.chunk_id for c in chunks]
        assert "c2" in chunk_ids or "c4" in chunk_ids

    def test_ranks_start_at_one(self):
        from app.retrieval.bm25 import Bm25Retriever

        retriever = Bm25Retriever()
        db = _make_mock_db()
        chunks, _ = retriever.search(db, "Python FastAPI web framework", top_k=5)

        if chunks:
            assert chunks[0].rank == 1

    def test_invalidate_clears_cache(self):
        from app.retrieval.bm25 import Bm25Retriever

        retriever = Bm25Retriever()
        db = _make_mock_db()
        # First search builds index
        retriever.search(db, "test", top_k=3)
        assert retriever._index is not None

        retriever.invalidate()
        assert retriever._index is None
        assert retriever._cached_count == -1

    def test_empty_db_returns_empty(self):
        from app.retrieval.bm25 import Bm25Retriever

        retriever = Bm25Retriever()

        # DB returns zero count and no rows
        mock_db = MagicMock()

        class _EmptyResult:
            def scalar_one(self):
                return 0
            def scalar_one_or_none(self):
                return None
            def scalars(self):
                class _Scalars:
                    def all(self):
                        return []
                return _Scalars()

        mock_db.execute.return_value = _EmptyResult()

        chunks, _ = retriever.search(mock_db, "anything", top_k=5)
        assert chunks == []


# ---------------------------------------------------------------------------
# RRF fusion tests
# ---------------------------------------------------------------------------

class TestReciprocatRankFusion:
    def _make_chunk(self, chunk_id: str, rank: int, score: float = 1.0) -> object:
        from app.schemas.retrieval import RetrievedChunk
        return RetrievedChunk(
            chunk_id=chunk_id,
            document_id="doc-1",
            text=f"text for {chunk_id}",
            score=score,
            source_file="test.pdf",
            rank=rank,
        )

    def test_fusion_math_known_order(self):
        """Synthetic example where we can compute the expected order by hand.

        Dense:  [A@1, B@2, C@3]
        Sparse: [B@1, C@2, A@3]

        With k=60, dense_weight=1, sparse_weight=1:
          score(A) = 1/(60+1) + 1/(60+3) = 0.016393 + 0.015625 = 0.032018
          score(B) = 1/(60+2) + 1/(60+1) = 0.016129 + 0.016393 = 0.032522
          score(C) = 1/(60+3) + 1/(60+2) = 0.015625 + 0.016129 = 0.031754

        Expected order: B > A > C
        """
        from app.retrieval.fusion import reciprocal_rank_fusion

        dense = [
            self._make_chunk("A", 1),
            self._make_chunk("B", 2),
            self._make_chunk("C", 3),
        ]
        sparse = [
            self._make_chunk("B", 1),
            self._make_chunk("C", 2),
            self._make_chunk("A", 3),
        ]
        fused = reciprocal_rank_fusion(
            dense=dense, sparse=sparse, k=60, dense_weight=1.0, sparse_weight=1.0, top_k=3
        )

        assert len(fused) == 3
        ids = [c.chunk_id for c in fused]
        assert ids == ["B", "A", "C"], f"Expected [B, A, C] but got {ids}"

    def test_fusion_score_values(self):
        """Verify actual score values match the formula."""
        from app.retrieval.fusion import reciprocal_rank_fusion

        dense = [self._make_chunk("A", 1), self._make_chunk("B", 2)]
        sparse = [self._make_chunk("B", 1), self._make_chunk("A", 2)]

        k = 60
        fused = reciprocal_rank_fusion(
            dense=dense, sparse=sparse, k=k, dense_weight=1.0, sparse_weight=1.0, top_k=2
        )

        score_a = 1 / (k + 1) + 1 / (k + 2)
        score_b = 1 / (k + 2) + 1 / (k + 1)
        # A and B should have the same score (symmetric)
        assert abs(fused[0].score - max(score_a, score_b)) < 1e-8

    def test_chunk_only_in_dense(self):
        """A chunk only in dense still appears with a non-zero score."""
        from app.retrieval.fusion import reciprocal_rank_fusion

        dense = [self._make_chunk("X", 1), self._make_chunk("Y", 2)]
        sparse = [self._make_chunk("Z", 1)]

        fused = reciprocal_rank_fusion(
            dense=dense, sparse=sparse, k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
        )

        ids = [c.chunk_id for c in fused]
        assert "X" in ids
        assert "Y" in ids
        assert "Z" in ids

    def test_ranks_reassigned(self):
        from app.retrieval.fusion import reciprocal_rank_fusion

        dense = [self._make_chunk(f"c{i}", i) for i in range(1, 6)]
        sparse = [self._make_chunk(f"c{i}", 6 - i) for i in range(1, 6)]

        fused = reciprocal_rank_fusion(
            dense=dense, sparse=sparse, k=60, top_k=5
        )
        ranks = [c.rank for c in fused]
        assert ranks == list(range(1, len(fused) + 1))

    def test_weights_affect_order(self):
        """Heavier dense_weight should favour dense-top chunks."""
        from app.retrieval.fusion import reciprocal_rank_fusion

        # A is #1 in dense, #3 in sparse
        # B is #3 in dense, #1 in sparse
        dense = [
            self._make_chunk("A", 1),
            self._make_chunk("C", 2),
            self._make_chunk("B", 3),
        ]
        sparse = [
            self._make_chunk("B", 1),
            self._make_chunk("C", 2),
            self._make_chunk("A", 3),
        ]

        # With very heavy dense weight, A should beat B
        fused = reciprocal_rank_fusion(
            dense=dense, sparse=sparse, k=60, dense_weight=10.0, sparse_weight=1.0, top_k=3
        )
        ids = [c.chunk_id for c in fused]
        assert ids[0] == "A", f"Expected A first with dense_weight=10, got {ids}"


# ---------------------------------------------------------------------------
# Reranker tests
# ---------------------------------------------------------------------------

class TestReranker:
    def _make_chunks(self) -> list:
        from app.schemas.retrieval import RetrievedChunk
        return [
            RetrievedChunk(
                chunk_id=c["chunk_id"],
                document_id=c.get("document_id", "doc-1"),
                text=c["text"],
                score=0.5,
                source_file=c.get("source_file", "test.pdf"),
                rank=i + 1,
            )
            for i, c in enumerate(CHUNKS)
        ]

    def test_rerank_returns_top_k(self):
        from app.retrieval.reranker import Reranker

        reranker = Reranker()
        chunks = self._make_chunks()
        result = reranker.rerank("Python programming", chunks, top_k=2)

        assert len(result) == 2

    def test_scores_in_zero_one(self):
        from app.retrieval.reranker import Reranker

        reranker = Reranker()
        chunks = self._make_chunks()
        result = reranker.rerank("machine learning algorithms", chunks, top_k=3)

        for c in result:
            assert 0.0 <= c.score <= 1.0, f"Score {c.score} out of [0,1]"

    def test_ranks_reassigned_from_one(self):
        from app.retrieval.reranker import Reranker

        reranker = Reranker()
        chunks = self._make_chunks()
        result = reranker.rerank("test", chunks, top_k=3)

        ranks = [c.rank for c in result]
        assert ranks == list(range(1, len(result) + 1))

    def test_empty_candidates(self):
        from app.retrieval.reranker import Reranker

        reranker = Reranker()
        result = reranker.rerank("anything", [], top_k=5)
        assert result == []


# ---------------------------------------------------------------------------
# Full pipeline smoke test
# ---------------------------------------------------------------------------

class TestHybridRetriever:
    def test_pipeline_runs_offline(self):
        from app.retrieval.pipeline import HybridRetriever
        from app.schemas.retrieval import RetrievalTrace

        retriever = HybridRetriever()
        db = _make_mock_db()
        chunks, trace, embedding_tokens = retriever.retrieve(db, "Python web framework")

        assert isinstance(trace, RetrievalTrace)
        assert isinstance(chunks, list)
        assert isinstance(embedding_tokens, int)

    def test_pipeline_produces_trace_stages(self):
        from app.retrieval.pipeline import HybridRetriever

        retriever = HybridRetriever()
        db = _make_mock_db()
        _, trace, _ = retriever.retrieve(db, "machine learning")

        assert trace.dense.name == "dense"
        assert trace.bm25.name == "bm25"
        assert trace.rrf.name == "rrf"
        assert trace.reranked.name == "reranked"

    def test_pipeline_returns_max_rerank_top_k(self):
        from app.core.config import settings
        from app.retrieval.pipeline import HybridRetriever

        retriever = HybridRetriever()
        db = _make_mock_db()
        chunks, _, _ = retriever.retrieve(db, "Docker containers deployment")

        assert len(chunks) <= settings.rerank_top_k

    def test_elapsed_ms_non_negative(self):
        from app.retrieval.pipeline import HybridRetriever

        retriever = HybridRetriever()
        db = _make_mock_db()
        _, trace, _ = retriever.retrieve(db, "test query")

        assert trace.dense.elapsed_ms >= 0
        assert trace.bm25.elapsed_ms >= 0
        assert trace.rrf.elapsed_ms >= 0
        assert trace.reranked.elapsed_ms >= 0
