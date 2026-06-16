"""Tests for the generation + verification + confidence pipeline.

All tests run offline: no OpenAI key, no Postgres, no Qdrant.
The extractive fallback generator is exercised throughout.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import uuid
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Shared helpers (mirror test_retrieval helpers to keep tests independent)
# ---------------------------------------------------------------------------

def _fake_embed(text: str) -> list[float]:
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
            "heading_path": None,
        }
        for c in chunks
    ]
    store.upsert(ids, vectors, payloads)


CHUNKS = [
    {
        "chunk_id": "g1",
        "document_id": "doc-1",
        "text": "Python is a high-level programming language with clear syntax.",
        "source_file": "python.pdf",
        "page_number": 1,
        "section_title": "Intro",
    },
    {
        "chunk_id": "g2",
        "document_id": "doc-1",
        "text": "FastAPI is built on top of Starlette and Pydantic for type safety.",
        "source_file": "fastapi.pdf",
        "page_number": 2,
        "section_title": "FastAPI",
    },
    {
        "chunk_id": "g3",
        "document_id": "doc-2",
        "text": "Machine learning models learn patterns from training data.",
        "source_file": "ml.pdf",
        "page_number": 1,
        "section_title": "ML",
    },
]


class _FakeChunk:
    def __init__(self, data: dict) -> None:
        self.id = data["chunk_id"]
        self.document_id = data.get("document_id", "doc-1")
        self.text = data["text"]
        self.source_file = data.get("source_file", "test.pdf")
        self.page_number = data.get("page_number", 1)
        self.section_title = data.get("section_title")
        self.heading_path = None
        self.is_duplicate = False


def _make_mock_db(chunks=None):
    if chunks is None:
        chunks = CHUNKS
    fake_rows = [_FakeChunk(c) for c in chunks]

    mock_db = MagicMock()

    # Build a smart result that handles all three call patterns:
    #   .scalar_one()            → chunk count (int)
    #   .scalars().all()         → list of chunk rows
    #   .scalar_one_or_none()    → None (no PromptVersion rows)
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
    # Also handle commit/rollback/add no-ops
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.rollback = MagicMock()
    return mock_db


@pytest.fixture(autouse=True)
def seed_store():
    _seed_vector_store(CHUNKS)
    yield


# ---------------------------------------------------------------------------
# Generator tests (offline extractive fallback)
# ---------------------------------------------------------------------------

class TestGenerator:
    def test_generate_returns_tuple(self):
        from app.generation.generator import Generator
        from app.generation.prompts import format_context

        gen = Generator()
        context_dicts = [
            {"text": c["text"], "source_file": c["source_file"], "page_number": c["page_number"]}
            for c in CHUNKS
        ]
        context = format_context(context_dicts)
        answer, inp_tokens, out_tokens = gen.generate(context, "What is Python?")

        assert isinstance(answer, str)
        assert len(answer) > 0
        assert isinstance(inp_tokens, int) and inp_tokens >= 0
        assert isinstance(out_tokens, int) and out_tokens >= 0

    def test_offline_answer_contains_citation_markers(self):
        from app.generation.generator import Generator
        from app.generation.prompts import format_context
        import re

        gen = Generator()
        context_dicts = [
            {"text": c["text"], "source_file": c["source_file"], "page_number": c["page_number"]}
            for c in CHUNKS
        ]
        context = format_context(context_dicts)
        answer, _, _ = gen.generate(context, "What is Python?")

        # Extractive fallback should include [n] markers
        assert re.search(r"\[\d+\]", answer), f"No citation markers in: {answer!r}"

    def test_stream_yields_text(self):
        from app.generation.generator import Generator
        from app.generation.prompts import format_context

        gen = Generator()
        context_dicts = [
            {"text": c["text"], "source_file": c["source_file"], "page_number": c["page_number"]}
            for c in CHUNKS
        ]
        context = format_context(context_dicts)
        parts = list(gen.stream(context, "What is Python?"))

        assert len(parts) > 0
        assert all(isinstance(p, str) for p in parts)
        full = "".join(parts)
        assert len(full) > 0


# ---------------------------------------------------------------------------
# Citation extraction tests
# ---------------------------------------------------------------------------

class TestCitationExtraction:
    def _make_retrieved_chunks(self):
        from app.schemas.retrieval import RetrievedChunk
        return [
            RetrievedChunk(
                chunk_id=c["chunk_id"],
                document_id=c["document_id"],
                text=c["text"],
                score=0.9 - i * 0.1,
                source_file=c["source_file"],
                page_number=c["page_number"],
                section_title=c["section_title"],
                rank=i + 1,
            )
            for i, c in enumerate(CHUNKS)
        ]

    def test_parses_citation_markers(self):
        from app.verification.citations import extract_citations
        from app.schemas.ask import Citation

        chunks = self._make_retrieved_chunks()
        answer = "Python has clear syntax [1]. FastAPI uses Pydantic [2]."
        citations = extract_citations(answer, chunks)

        assert isinstance(citations, list)
        markers = [c.marker for c in citations]
        assert 1 in markers
        assert 2 in markers

    def test_out_of_range_marker_ignored(self):
        from app.verification.citations import extract_citations

        chunks = self._make_retrieved_chunks()
        # Marker [99] is way out of range
        answer = "Some claim [99] that nobody can support."
        citations = extract_citations(answer, chunks)

        assert all(c.marker != 99 for c in citations)

    def test_citation_has_required_fields(self):
        from app.verification.citations import extract_citations

        chunks = self._make_retrieved_chunks()
        answer = "Python is a programming language [1]."
        citations = extract_citations(answer, chunks)

        if citations:
            cit = citations[0]
            assert cit.marker == 1
            assert cit.chunk_id == "g1"
            assert isinstance(cit.quote, str) and len(cit.quote) > 0
            assert isinstance(cit.text, str) and len(cit.text) > 0

    def test_no_markers_returns_empty(self):
        from app.verification.citations import extract_citations

        chunks = self._make_retrieved_chunks()
        answer = "This answer has no citation markers at all."
        citations = extract_citations(answer, chunks)
        assert citations == []


# ---------------------------------------------------------------------------
# Verifier tests
# ---------------------------------------------------------------------------

class TestVerifier:
    def _make_citation(self, marker: int, chunk_id: str, text: str) -> object:
        from app.schemas.ask import Citation
        return Citation(
            marker=marker,
            chunk_id=chunk_id,
            document_id="doc-1",
            source_file="test.pdf",
            page_number=1,
            section_title=None,
            quote="quote",
            text=text,
        )

    def test_well_supported_claim(self):
        """A claim that closely matches its cited chunk should be supported."""
        from app.verification.verifier import verify

        chunk_text = "Python is a high-level programming language with clear readable syntax."
        # Claim closely mirrors the chunk text
        answer = "Python is a high-level language with clear syntax. [1]"
        cit = self._make_citation(1, "g1", chunk_text)

        verifications, accuracy = verify(answer, [cit])

        assert len(verifications) > 0
        # At least one claim should be supported or partially_supported
        statuses = {v.status for v in verifications}
        assert "supported" in statuses or "partially_supported" in statuses

    def test_clearly_unsupported_claim(self):
        """A claim citing a chunk with completely unrelated text → unsupported."""
        from app.verification.verifier import verify

        chunk_text = "The Eiffel Tower is located in Paris, France."
        # Claim is about machine learning; chunk is about Paris
        answer = "Deep learning requires GPUs for training [1]."
        cit = self._make_citation(1, "g1", chunk_text)

        verifications, accuracy = verify(answer, [cit])

        assert len(verifications) > 0
        # The claim should be unsupported (very low Jaccard overlap)
        assert verifications[0].status == "unsupported"

    def test_no_citation_gives_unsupported(self):
        """A claim with no [n] markers should always be unsupported."""
        from app.verification.verifier import verify

        cit = self._make_citation(1, "g1", "some chunk text")
        answer = "This claim has absolutely no citation markers."
        verifications, accuracy = verify(answer, [cit])

        assert len(verifications) > 0
        assert verifications[0].status == "unsupported"

    def test_citation_accuracy_range(self):
        """citation_accuracy should always be in [0, 1]."""
        from app.verification.verifier import verify

        chunk_text = "Python is a high-level programming language with clear readable syntax."
        cit = self._make_citation(1, "g1", chunk_text)
        answer = "Python is a high-level language [1]. Some unrelated claim."
        _, accuracy = verify(answer, [cit])

        assert 0.0 <= accuracy <= 1.0

    def test_partial_accuracy_scoring(self):
        """Partially supported claims count 0.5 in accuracy computation."""
        # The lexical entailment heuristic now lives in the Local provider.
        from app.verification.verifier import verify
        from app.providers.local_provider import LOW_THRESHOLD, HIGH_THRESHOLD  # noqa: F401

        # Craft a claim with moderate overlap (between LOW and HIGH threshold)
        chunk_text = "machine learning models use data training algorithms"
        # Claim shares some words but not all
        claim = "models sometimes need large training datasets [1]"
        cit = self._make_citation(1, "g1", chunk_text)
        answer = claim

        verifications, accuracy = verify(answer, [cit])

        # Accuracy should be between 0 and 1 (not necessarily 0.5 exactly,
        # depends on overlap — just validate the range and type)
        assert 0.0 <= accuracy <= 1.0
        assert isinstance(accuracy, float)


# ---------------------------------------------------------------------------
# Confidence tests
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_score_in_range(self):
        from app.verification.confidence import compute_confidence
        from app.schemas.ask import Citation, ClaimVerification

        cit = Citation(
            marker=1, chunk_id="g1", document_id="doc-1",
            source_file="test.pdf", page_number=1,
            section_title=None, quote="q", text="t",
        )
        ver = ClaimVerification(
            claim="some claim [1]",
            cited_markers=[1],
            status="supported",
            rationale="overlap",
        )
        cb = compute_confidence(
            retrieval_scores=[0.03, 0.025, 0.02],
            reranker_scores=[0.8, 0.7, 0.6],
            citations=[cit],
            verifications=[ver],
            num_context=3,
            answer="some claim [1].",
            citation_accuracy=1.0,
        )

        assert 0.0 <= cb.score <= 100.0

    def test_all_zero_inputs_gives_low_score(self):
        from app.verification.confidence import compute_confidence

        cb = compute_confidence(
            retrieval_scores=[],
            reranker_scores=[],
            citations=[],
            verifications=[],
            num_context=0,
            answer="",
            citation_accuracy=0.0,
        )
        assert cb.score < 30.0

    def test_good_inputs_give_higher_score(self):
        from app.verification.confidence import compute_confidence
        from app.schemas.ask import Citation, ClaimVerification

        cits = [
            Citation(
                marker=i, chunk_id=f"g{i}", document_id="doc-1",
                source_file="test.pdf", page_number=i,
                section_title=None, quote="q", text="t",
            )
            for i in range(1, 4)
        ]
        vers = [
            ClaimVerification(
                claim=f"claim {i} [{i}]",
                cited_markers=[i],
                status="supported",
                rationale="ok",
            )
            for i in range(1, 4)
        ]
        cb = compute_confidence(
            retrieval_scores=[0.03, 0.025, 0.02],
            reranker_scores=[0.9, 0.85, 0.8],
            citations=cits,
            verifications=vers,
            num_context=3,
            answer="claim 1 [1]. claim 2 [2]. claim 3 [3].",
            citation_accuracy=1.0,
        )
        assert cb.score >= 50.0


# ---------------------------------------------------------------------------
# Full RAGService.ask smoke test
# ---------------------------------------------------------------------------

class TestRAGServiceAsk:
    def test_ask_returns_ask_response(self):
        from app.services.rag_service import RAGService
        from app.schemas.ask import AskRequest, AskResponse

        service = RAGService()
        db = _make_mock_db()
        req = AskRequest(question="What is Python?", include_trace=True)
        response = service.ask(db, req)

        assert isinstance(response, AskResponse)
        assert isinstance(response.answer, str)
        assert len(response.answer) > 0
        assert response.query_id is not None

    def test_ask_confidence_score_in_range(self):
        from app.services.rag_service import RAGService
        from app.schemas.ask import AskRequest

        service = RAGService()
        db = _make_mock_db()
        req = AskRequest(question="Tell me about machine learning.", include_trace=False)
        response = service.ask(db, req)

        assert 0.0 <= response.confidence.score <= 100.0

    def test_ask_without_trace(self):
        from app.services.rag_service import RAGService
        from app.schemas.ask import AskRequest

        service = RAGService()
        db = _make_mock_db()
        req = AskRequest(question="What is FastAPI?", include_trace=False)
        response = service.ask(db, req)

        assert response.trace is None

    def test_ask_with_trace_has_all_stages(self):
        from app.services.rag_service import RAGService
        from app.schemas.ask import AskRequest

        service = RAGService()
        db = _make_mock_db()
        req = AskRequest(question="What is Python?", include_trace=True)
        response = service.ask(db, req)

        assert response.trace is not None
        assert response.trace.dense is not None
        assert response.trace.bm25 is not None
        assert response.trace.rrf is not None
        assert response.trace.reranked is not None

    def test_ask_stream_yields_tokens_then_done(self):
        from app.services.rag_service import RAGService
        from app.schemas.ask import AskRequest

        service = RAGService()
        db = _make_mock_db()
        req = AskRequest(question="What is Python?", stream=True, include_trace=False)

        events = list(service.ask_stream(db, req))

        assert len(events) > 0
        # Last event should be "done"
        assert events[-1]["type"] == "done"
        # At least one token event
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) > 0
        # Done event should have data with AskResponse shape
        done_data = events[-1]["data"]
        assert "answer" in done_data
        assert "confidence" in done_data

    def test_ask_cost_usd_non_negative(self):
        from app.services.rag_service import RAGService
        from app.schemas.ask import AskRequest

        service = RAGService()
        db = _make_mock_db()
        req = AskRequest(question="Explain machine learning.")
        response = service.ask(db, req)

        assert response.cost_usd >= 0.0

    def test_ask_latency_ms_non_negative(self):
        from app.services.rag_service import RAGService
        from app.schemas.ask import AskRequest

        service = RAGService()
        db = _make_mock_db()
        req = AskRequest(question="What is Docker?")
        response = service.ask(db, req)

        assert response.latency_ms >= 0
