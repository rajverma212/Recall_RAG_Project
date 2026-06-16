"""Tests for all three chunkers on a small synthetic text."""
from __future__ import annotations

import sys
import os

import pytest

# Ensure the backend/ directory is on the path so `app.*` imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ingestion.loaders.base import LoadedSection


def _make_sections(texts: list[str]) -> list[LoadedSection]:
    return [
        LoadedSection(
            text=t,
            page_number=i + 1,
            section_title=f"Section {i + 1}",
            heading_path=f"Doc > Section {i + 1}",
            ordinal=i,
        )
        for i, t in enumerate(texts)
    ]


LONG_TEXT = (
    "The quick brown fox jumps over the lazy dog. " * 60
    + "Sphinx of black quartz, judge my vow. " * 20
)

SHORT_SECTIONS = [
    "This is the first paragraph of our test document.",
    "Here is the second paragraph with some additional content that stretches a bit further.",
    "And a third paragraph to round things out.",
]


# ─── FixedChunker ───────────────────────────────────────────────────────────

class TestFixedChunker:
    def test_produces_chunks(self):
        from app.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=50, chunk_overlap=10)
        sections = _make_sections([LONG_TEXT])
        pieces = chunker.chunk(sections)
        assert len(pieces) > 1, "Expected multiple chunks from a long text"

    def test_short_text_single_chunk(self):
        from app.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=512, chunk_overlap=64)
        sections = _make_sections(["Hello world."])
        pieces = chunker.chunk(sections)
        assert len(pieces) == 1
        assert pieces[0].text == "Hello world."

    def test_chunk_size_respected(self):
        from app.chunking.fixed import FixedChunker
        chunk_size = 30
        chunker = FixedChunker(chunk_size=chunk_size, chunk_overlap=5)
        sections = _make_sections([LONG_TEXT])
        pieces = chunker.chunk(sections)
        for p in pieces:
            # Allow a small margin for tokenisation differences
            assert p.token_count <= chunk_size + 5, (
                f"Chunk token_count {p.token_count} exceeds {chunk_size + 5}"
            )

    def test_provenance_preserved(self):
        from app.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=50, chunk_overlap=10)
        sections = _make_sections([LONG_TEXT])
        pieces = chunker.chunk(sections)
        for p in pieces:
            assert p.page_number == 1
            assert p.section_title == "Section 1"

    def test_empty_sections(self):
        from app.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=50, chunk_overlap=10)
        sections = _make_sections(["   ", ""])
        pieces = chunker.chunk(sections)
        assert pieces == []

    def test_ordinals_are_sequential(self):
        from app.chunking.fixed import FixedChunker
        chunker = FixedChunker(chunk_size=30, chunk_overlap=5)
        sections = _make_sections(SHORT_SECTIONS)
        pieces = chunker.chunk(sections)
        for i, p in enumerate(pieces):
            assert p.ordinal == i


# ─── RecursiveChunker ────────────────────────────────────────────────────────

class TestRecursiveChunker:
    def test_produces_chunks(self):
        from app.chunking.recursive import RecursiveChunker
        chunker = RecursiveChunker(chunk_size=50, chunk_overlap=10)
        sections = _make_sections([LONG_TEXT])
        pieces = chunker.chunk(sections)
        assert len(pieces) > 1

    def test_small_text_single_chunk(self):
        from app.chunking.recursive import RecursiveChunker
        chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
        sections = _make_sections(["Short text."])
        pieces = chunker.chunk(sections)
        assert len(pieces) >= 1
        assert "Short text." in pieces[0].text

    def test_paragraph_split(self):
        from app.chunking.recursive import RecursiveChunker
        # Each paragraph is ~3-4 tokens; chunk_size=3 forces splits between paragraphs
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunker = RecursiveChunker(chunk_size=3, chunk_overlap=0)
        sections = _make_sections([text])
        pieces = chunker.chunk(sections)
        assert len(pieces) >= 2, "Expected double-newline splits to produce multiple chunks"

    def test_provenance_preserved(self):
        from app.chunking.recursive import RecursiveChunker
        chunker = RecursiveChunker(chunk_size=50, chunk_overlap=10)
        sections = _make_sections(SHORT_SECTIONS)
        pieces = chunker.chunk(sections)
        # Each chunk should have provenance from one of the sections
        for p in pieces:
            assert p.section_title is not None

    def test_empty_sections(self):
        from app.chunking.recursive import RecursiveChunker
        chunker = RecursiveChunker(chunk_size=50, chunk_overlap=10)
        sections = _make_sections([""])
        pieces = chunker.chunk(sections)
        assert pieces == []


# ─── SemanticChunker ─────────────────────────────────────────────────────────

class TestSemanticChunker:
    def test_produces_chunks(self):
        from app.chunking.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=50, breakpoint_percentile=50.0)
        text = ". ".join([f"This is sentence number {i}" for i in range(20)]) + "."
        sections = _make_sections([text])
        pieces = chunker.chunk(sections)
        assert len(pieces) >= 1

    def test_single_sentence_emits_one_chunk(self):
        from app.chunking.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=512, breakpoint_percentile=95.0)
        sections = _make_sections(["Only one sentence here."])
        pieces = chunker.chunk(sections)
        assert len(pieces) == 1
        assert "Only one sentence here." in pieces[0].text

    def test_provenance_preserved(self):
        from app.chunking.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=50, breakpoint_percentile=50.0)
        text = ". ".join([f"Sentence {i}" for i in range(10)]) + "."
        sections = _make_sections([text])
        sections[0].page_number = 42
        sections[0].section_title = "My Section"
        pieces = chunker.chunk(sections)
        for p in pieces:
            assert p.page_number == 42
            assert p.section_title == "My Section"

    def test_empty_sections(self):
        from app.chunking.semantic import SemanticChunker
        chunker = SemanticChunker(chunk_size=512, breakpoint_percentile=95.0)
        sections = _make_sections([""])
        pieces = chunker.chunk(sections)
        assert pieces == []


# ─── Factory ─────────────────────────────────────────────────────────────────

class TestGetChunker:
    def test_factory_fixed(self):
        from app.chunking import get_chunker
        from app.chunking.fixed import FixedChunker
        assert isinstance(get_chunker("fixed"), FixedChunker)

    def test_factory_recursive(self):
        from app.chunking import get_chunker
        from app.chunking.recursive import RecursiveChunker
        assert isinstance(get_chunker("recursive"), RecursiveChunker)

    def test_factory_semantic(self):
        from app.chunking import get_chunker
        from app.chunking.semantic import SemanticChunker
        assert isinstance(get_chunker("semantic"), SemanticChunker)

    def test_factory_unknown(self):
        from app.chunking import get_chunker
        with pytest.raises(ValueError, match="Unsupported"):
            get_chunker("bogus")


# ─── Loader smoke tests ───────────────────────────────────────────────────────

class TestLoaders:
    def test_txt_loader(self):
        from app.ingestion.loaders import get_loader
        loader = get_loader("txt")
        raw = b"Hello world.\n\nSecond paragraph."
        sections = loader.load(raw, "test.txt")
        assert len(sections) == 2
        assert sections[0].text == "Hello world."
        assert sections[1].text == "Second paragraph."

    def test_markdown_loader(self):
        from app.ingestion.loaders import get_loader
        loader = get_loader("markdown")
        raw = b"# Title\n\nSome text.\n\n## Section\n\nMore text."
        sections = loader.load(raw, "test.md")
        assert len(sections) >= 1
        # At least one section should reference "Title" or "Section"
        titles = [s.section_title for s in sections if s.section_title]
        assert len(titles) >= 1

    def test_html_loader(self):
        from app.ingestion.loaders import get_loader
        loader = get_loader("html")
        raw = b"<html><body><h1>Title</h1><p>Para one.</p><h2>Sub</h2><p>Para two.</p></body></html>"
        sections = loader.load(raw, "test.html")
        assert len(sections) >= 1

    def test_unknown_loader(self):
        from app.ingestion.loaders import get_loader
        with pytest.raises(ValueError):
            get_loader("docx")

    def test_detect_doc_type_pdf(self):
        from app.ingestion.detect import detect_doc_type
        assert detect_doc_type("resume.pdf", "application/pdf") == "pdf"

    def test_detect_doc_type_markdown(self):
        from app.ingestion.detect import detect_doc_type
        assert detect_doc_type("notes.md", "text/plain") == "markdown"

    def test_detect_doc_type_html(self):
        from app.ingestion.detect import detect_doc_type
        assert detect_doc_type("page.html", "text/html") == "html"

    def test_detect_doc_type_txt(self):
        from app.ingestion.detect import detect_doc_type
        assert detect_doc_type("readme.txt", "text/plain") == "txt"

    def test_detect_doc_type_unsupported(self):
        from app.ingestion.detect import detect_doc_type
        with pytest.raises(ValueError):
            detect_doc_type("file.docx", "application/vnd.openxmlformats")
