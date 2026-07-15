"""Ingestion service — orchestrates loading, chunking, embedding, dedup, and persistence."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.chunking import get_chunker
from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.dedup import Deduplicator
from app.ingestion.detect import detect_doc_type
from app.ingestion.loaders import get_loader
from app.models.chunk import Chunk
from app.models.document import Document, IngestionStatus
from app.schemas.document import IngestResponse
from app.services.embeddings import get_embedding_client
from app.services.vector_store import get_vector_store

logger = get_logger(__name__)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class IngestionService:
    """Handles full ingestion pipeline for uploaded documents."""

    def ingest_upload(
        self,
        db: Session,
        *,
        filename: str,
        content_type: str,
        raw_bytes: bytes,
        strategy: str | None = None,
    ) -> IngestResponse:
        """Ingest an uploaded document.

        Raises ValueError for unsupported doc types (caller routes to 400).
        All other exceptions are caught, stored as error on the Document, and
        re-raised so the caller can return 500.
        """
        # ---- Detect document type (ValueError propagates as 400) ----
        doc_type = detect_doc_type(filename, content_type)

        # ---- Compute content hash ----
        sha = _sha256(raw_bytes)

        # ---- Idempotency: same SHA256 + completed ----
        existing = (
            db.query(Document)
            .filter(Document.sha256 == sha, Document.status == IngestionStatus.completed)
            .first()
        )
        if existing is not None:
            logger.info(f"Document {filename!r} already ingested as {existing.id!r}, returning cached result")
            return IngestResponse(
                document_id=existing.id,
                filename=existing.filename,
                status=existing.status.value,
                num_chunks=existing.num_chunks,
                num_duplicates_skipped=0,
                message="already ingested",
            )

        # ---- Choose chunking strategy ----
        chunk_strategy = strategy or settings.chunking_strategy

        # ---- Persist raw bytes ----
        doc_id = str(uuid.uuid4())
        _ensure_dir(settings.raw_storage_dir)
        raw_path = os.path.join(settings.raw_storage_dir, f"{doc_id}_{filename}")
        with open(raw_path, "wb") as fh:
            fh.write(raw_bytes)

        # ---- Create Document row (status=processing) ----
        doc = Document(
            id=doc_id,
            filename=filename,
            content_type=content_type,
            doc_type=doc_type,
            raw_path=raw_path,
            sha256=sha,
            status=IngestionStatus.processing,
            chunking_strategy=chunk_strategy,
            ingested_at=datetime.utcnow(),
        )
        db.add(doc)
        db.flush()  # get the ID into the session without committing

        try:
            # ---- Load sections ----
            loader = get_loader(doc_type)
            sections = loader.load(raw_bytes, filename)
            num_pages = max((s.page_number or 0) for s in sections) if sections else None
            title = sections[0].section_title if sections else filename

            # ---- Chunk ----
            chunker = get_chunker(chunk_strategy)
            chunk_pieces = chunker.chunk(sections)

            if not chunk_pieces:
                logger.warning(f"No chunks produced for {filename!r}")

            # ---- Embed all texts in one batch ----
            texts = [cp.text for cp in chunk_pieces]
            embedding_result = get_embedding_client().embed(texts) if texts else None
            vectors = embedding_result.vectors if embedding_result else []

            logger.info(
                f"Embedded {len(texts)} chunks for {filename!r} "
                f"(tokens={embedding_result.tokens if embedding_result else 0}, "
                f"cost=${embedding_result.cost_usd if embedding_result else 0:.6f})"
            )

            # ---- Deduplication ----
            chunk_ids = [str(uuid.uuid4()) for _ in chunk_pieces]
            dedup = Deduplicator()
            dedup_results = dedup.check(chunk_ids, texts, vectors) if vectors else [
                (False, None, 0.0) for _ in chunk_pieces
            ]

            # ---- Persist Chunk rows ----
            non_dup_ids: list[str] = []
            non_dup_vectors: list[list[float]] = []
            non_dup_payloads: list[dict] = []
            num_duplicates_skipped = 0
            processed_chunks_data: list[dict] = []

            for i, (cp, cid, (is_dup, dup_of, dup_sim)) in enumerate(
                zip(chunk_pieces, chunk_ids, dedup_results)
            ):
                vec = vectors[i] if i < len(vectors) else []

                chunk = Chunk(
                    id=cid,
                    document_id=doc_id,
                    text=cp.text,
                    token_count=cp.token_count,
                    ordinal=cp.ordinal,
                    source_file=filename,
                    page_number=cp.page_number,
                    section_title=cp.section_title,
                    heading_path=cp.heading_path,
                    strategy=chunk_strategy,
                    chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap,
                    is_duplicate=is_dup,
                    duplicate_of=dup_of,
                    dedup_similarity=dup_sim if is_dup else None,
                    embedded=not is_dup,
                    created_at=datetime.utcnow(),
                )
                db.add(chunk)

                if is_dup:
                    num_duplicates_skipped += 1
                else:
                    payload = {
                        "document_id": doc_id,
                        "chunk_id": cid,
                        "source_file": filename,
                        "page_number": cp.page_number,
                        "section_title": cp.section_title,
                        "text": cp.text,
                    }
                    non_dup_ids.append(cid)
                    non_dup_vectors.append(vec)
                    non_dup_payloads.append(payload)

                processed_chunks_data.append({
                    "id": cid,
                    "ordinal": cp.ordinal,
                    "text": cp.text,
                    "token_count": cp.token_count,
                    "page_number": cp.page_number,
                    "section_title": cp.section_title,
                    "heading_path": cp.heading_path,
                    "is_duplicate": is_dup,
                    "duplicate_of": dup_of,
                    "dedup_similarity": dup_sim if is_dup else None,
                })

            # ---- Upsert non-duplicate vectors into vector store ----
            if non_dup_ids:
                get_vector_store().upsert(non_dup_ids, non_dup_vectors, non_dup_payloads)

            # ---- Write processed chunks JSON ----
            _ensure_dir(settings.processed_storage_dir)
            processed_path = os.path.join(settings.processed_storage_dir, f"{doc_id}.json")
            with open(processed_path, "w", encoding="utf-8") as fh:
                json.dump(processed_chunks_data, fh, ensure_ascii=False, indent=2)

            # ---- Update Document ----
            num_non_dup = len(non_dup_ids)
            doc.num_chunks = num_non_dup
            doc.num_pages = num_pages
            doc.title = title
            doc.status = IngestionStatus.completed
            doc.completed_at = datetime.utcnow()

            db.commit()

            logger.info(
                f"Ingested {filename!r}: {num_non_dup} chunks accepted, "
                f"{num_duplicates_skipped} duplicates skipped"
            )

            return IngestResponse(
                document_id=doc_id,
                filename=filename,
                status=IngestionStatus.completed.value,
                num_chunks=num_non_dup,
                num_duplicates_skipped=num_duplicates_skipped,
                message=None,
            )

        except Exception as exc:
            logger.error(f"Ingestion failed for {filename!r}: {exc}")
            doc.status = IngestionStatus.failed
            doc.error = str(exc)
            try:
                db.commit()
            except Exception:
                db.rollback()
            raise

    def delete_document(self, db: Session, document_id: str) -> bool:
        """Delete a document and all its chunks from DB and vector store.

        Returns True if the document existed, False otherwise.
        """
        doc = db.get(Document, document_id)
        if doc is None:
            logger.warning(f"delete_document: document {document_id!r} not found")
            return False

        # Remove vectors from vector store
        get_vector_store().delete_document(document_id)

        # Delete Document row (cascade removes chunks)
        db.delete(doc)
        db.commit()

        logger.info(f"Deleted document {document_id!r} and all its chunks")
        return True

    def delete_all_documents(self, db: Session) -> int:
        """Delete every document (and its chunks/vectors). Returns count deleted."""
        from sqlalchemy import select

        doc_ids = list(db.scalars(select(Document.id)).all())
        for doc_id in doc_ids:
            self.delete_document(db, doc_id)
        logger.info(f"Cleared corpus: deleted {len(doc_ids)} documents")
        return len(doc_ids)


_ingestion_service: IngestionService | None = None


def get_ingestion_service() -> IngestionService:
    """Return the global singleton IngestionService."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = IngestionService()
    return _ingestion_service
