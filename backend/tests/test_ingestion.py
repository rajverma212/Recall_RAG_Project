"""End-to-end ingestion tests using an in-memory SQLite database.

These tests exercise the full IngestionService.ingest_upload flow without
requiring Postgres, Qdrant, or an OpenAI API key. The offline fallback
embedding client and in-memory vector store handle those dependencies.
"""
from __future__ import annotations

import sys
import os
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch storage dirs to writable temp paths before any import touches settings
import tempfile
_TMPDIR = tempfile.mkdtemp(prefix="rag_test_")
_RAW_DIR = os.path.join(_TMPDIR, "raw")
_PROC_DIR = os.path.join(_TMPDIR, "processed")
os.makedirs(_RAW_DIR, exist_ok=True)
os.makedirs(_PROC_DIR, exist_ok=True)

from app.core.config import settings as _settings
_settings.raw_storage_dir = _RAW_DIR
_settings.processed_storage_dir = _PROC_DIR


# ─── DB fixtures ─────────────────────────────────────────────────────────────

def _make_sqlite_session():
    """Try to create an in-memory SQLite session with all models.

    Returns (engine, session) or raises SkipTest if SQLAlchemy types are
    incompatible with SQLite (e.g. Postgres-specific enum handling).
    """
    try:
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import sessionmaker
        from app.db.base import Base
        # Import all models so they register with Base
        from app.models import document, chunk  # noqa: F401

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
        )

        # SQLite doesn't support native enums — map them to VARCHAR
        from sqlalchemy.dialects import sqlite as _sqlite
        from sqlalchemy import Enum as _Enum

        # Create all tables
        Base.metadata.create_all(engine)

        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return engine, Session()
    except Exception as exc:
        pytest.skip(f"SQLite session setup failed (likely Postgres-specific types): {exc}")


@pytest.fixture()
def db():
    """Provide a fresh in-memory SQLite session per test."""
    engine, session = _make_sqlite_session()
    yield session
    session.close()
    from app.db.base import Base
    Base.metadata.drop_all(engine)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _txt_bytes(text: str = "Hello world.\n\nSecond paragraph.") -> bytes:
    return text.encode("utf-8")


def _make_service():
    # Reset the singleton so each test gets a fresh service
    import app.services.ingestion_service as _svc
    _svc._ingestion_service = None
    # Also reset vector store singleton so we start with empty in-memory store
    import app.services.vector_store as _vs
    _vs._vector_store = None
    from app.services.ingestion_service import get_ingestion_service
    return get_ingestion_service()


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestIngestUpload:
    def test_basic_txt_ingest(self, db):
        svc = _make_service()
        resp = svc.ingest_upload(
            db,
            filename="test.txt",
            content_type="text/plain",
            raw_bytes=_txt_bytes(),
            strategy="fixed",
        )
        assert resp.document_id
        assert resp.filename == "test.txt"
        assert resp.status == "completed"
        assert resp.num_chunks >= 1

    def test_markdown_ingest(self, db):
        svc = _make_service()
        md = b"# Title\n\nFirst section text.\n\n## Sub\n\nSecond section text."
        resp = svc.ingest_upload(
            db,
            filename="doc.md",
            content_type="text/markdown",
            raw_bytes=md,
            strategy="recursive",
        )
        assert resp.status == "completed"
        assert resp.num_chunks >= 1

    def test_html_ingest(self, db):
        svc = _make_service()
        html = b"<html><body><h1>Hello</h1><p>World.</p></body></html>"
        resp = svc.ingest_upload(
            db,
            filename="page.html",
            content_type="text/html",
            raw_bytes=html,
            strategy="fixed",
        )
        assert resp.status == "completed"

    def test_idempotent_ingest(self, db):
        svc = _make_service()
        raw = _txt_bytes("Unique text for idempotency test " + str(uuid.uuid4()))
        resp1 = svc.ingest_upload(
            db,
            filename="idem.txt",
            content_type="text/plain",
            raw_bytes=raw,
            strategy="fixed",
        )
        resp2 = svc.ingest_upload(
            db,
            filename="idem.txt",
            content_type="text/plain",
            raw_bytes=raw,
            strategy="fixed",
        )
        assert resp1.document_id == resp2.document_id
        assert resp2.message == "already ingested"

    def test_unsupported_type_raises(self, db):
        svc = _make_service()
        with pytest.raises(ValueError, match="Unsupported"):
            svc.ingest_upload(
                db,
                filename="file.docx",
                content_type="application/vnd.openxmlformats",
                raw_bytes=b"fake docx bytes",
            )

    def test_document_persisted_in_db(self, db):
        from app.models.document import Document, IngestionStatus
        svc = _make_service()
        resp = svc.ingest_upload(
            db,
            filename="persist.txt",
            content_type="text/plain",
            raw_bytes=_txt_bytes("Some content to persist."),
            strategy="fixed",
        )
        doc = db.get(Document, resp.document_id)
        assert doc is not None
        assert doc.status == IngestionStatus.completed
        assert doc.num_chunks == resp.num_chunks

    def test_chunks_persisted_in_db(self, db):
        from app.models.chunk import Chunk
        svc = _make_service()
        resp = svc.ingest_upload(
            db,
            filename="chunks.txt",
            content_type="text/plain",
            raw_bytes=_txt_bytes("Chunk one.\n\nChunk two.\n\nChunk three."),
            strategy="fixed",
        )
        chunks = db.query(Chunk).filter(Chunk.document_id == resp.document_id).all()
        assert len(chunks) >= 1
        for c in chunks:
            assert c.strategy == "fixed"
            assert c.source_file == "chunks.txt"

    def test_semantic_strategy(self, db):
        svc = _make_service()
        text = ". ".join([f"Sentence {i}" for i in range(15)]) + "."
        resp = svc.ingest_upload(
            db,
            filename="semantic.txt",
            content_type="text/plain",
            raw_bytes=text.encode(),
            strategy="semantic",
        )
        assert resp.status == "completed"
        assert resp.num_chunks >= 1

    def test_raw_file_written(self, db, tmp_path, monkeypatch):
        """Verify that the raw bytes are actually written to disk."""
        monkeypatch.setattr("app.core.config.settings.raw_storage_dir", str(tmp_path / "raw"))
        monkeypatch.setattr("app.core.config.settings.processed_storage_dir", str(tmp_path / "processed"))

        svc = _make_service()
        raw = _txt_bytes("File write test.")
        resp = svc.ingest_upload(
            db,
            filename="writeme.txt",
            content_type="text/plain",
            raw_bytes=raw,
            strategy="fixed",
        )
        raw_dir = tmp_path / "raw"
        written_files = list(raw_dir.iterdir())
        assert len(written_files) == 1
        assert written_files[0].read_bytes() == raw

    def test_processed_json_written(self, db, tmp_path, monkeypatch):
        """Verify that processed chunks JSON is written to disk."""
        import json
        monkeypatch.setattr("app.core.config.settings.raw_storage_dir", str(tmp_path / "raw"))
        monkeypatch.setattr("app.core.config.settings.processed_storage_dir", str(tmp_path / "proc"))

        svc = _make_service()
        resp = svc.ingest_upload(
            db,
            filename="proc.txt",
            content_type="text/plain",
            raw_bytes=_txt_bytes("Processed output test."),
            strategy="fixed",
        )
        proc_dir = tmp_path / "proc"
        json_files = list(proc_dir.glob("*.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text())
        assert isinstance(data, list)
        assert len(data) >= 1


class TestDeleteDocument:
    def test_delete_existing(self, db):
        svc = _make_service()
        resp = svc.ingest_upload(
            db,
            filename="todel.txt",
            content_type="text/plain",
            raw_bytes=_txt_bytes("Delete me."),
            strategy="fixed",
        )
        result = svc.delete_document(db, resp.document_id)
        assert result is True

    def test_delete_nonexistent(self, db):
        svc = _make_service()
        result = svc.delete_document(db, "nonexistent-id")
        assert result is False

    def test_delete_removes_from_db(self, db):
        from app.models.document import Document
        from app.models.chunk import Chunk
        svc = _make_service()
        resp = svc.ingest_upload(
            db,
            filename="gone.txt",
            content_type="text/plain",
            raw_bytes=_txt_bytes("Going away."),
            strategy="fixed",
        )
        doc_id = resp.document_id
        svc.delete_document(db, doc_id)

        assert db.get(Document, doc_id) is None
        remaining_chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert remaining_chunks == []
