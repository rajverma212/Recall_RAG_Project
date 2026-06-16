"""Seed sample corpus files into sample_data/raw/ and ingest them.

Usage (from repo root):
    python scripts/seed_sample_data.py

This script:
1. Verifies that all expected corpus files exist in sample_data/raw/.
2. Ingests each file via IngestionService (idempotent — skips already-ingested files).
3. Reports the ingestion status of each file.

If the database is unavailable, prints a warning and exits without error
(evaluation can still run offline using the in-memory vector store).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Insert backend/ so `from app...` imports work
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.core.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

_SAMPLE_DATA_DIR = _REPO_ROOT / "sample_data" / "raw"

_EXPECTED_FILES = [
    "employee_handbook.md",
    "api_reference.md",
    "runbook_incidents.txt",
    "security_policy.txt",
    "onboarding_guide.html",
    "engineering_standards.md",
    "architecture_overview.md",
    "product_roadmap.html",
]


def _get_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".html": "text/html",
        ".pdf": "application/pdf",
    }
    return mapping.get(ext, "application/octet-stream")


def seed(db=None) -> dict[str, str]:
    """Ingest all sample corpus files. Returns dict of filename → status.

    If db is None, uses offline in-memory ingestion (no DB required).
    """
    results: dict[str, str] = {}

    if not _SAMPLE_DATA_DIR.exists():
        logger.error(f"Sample data directory not found: {_SAMPLE_DATA_DIR}")
        return results

    files = [_SAMPLE_DATA_DIR / fn for fn in _EXPECTED_FILES]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        logger.warning(f"Missing files (will be skipped): {missing}")

    if db is not None:
        return _seed_online(db, files, results)
    else:
        return _seed_offline(files, results)


def _seed_online(db, files: list, results: dict) -> dict:
    """Full DB-backed ingestion via IngestionService."""
    from app.services.ingestion_service import get_ingestion_service

    ingestion_svc = get_ingestion_service()
    for path in files:
        if not path.exists():
            results[path.name] = "missing"
            continue
        content_type = _get_content_type(path.name)
        try:
            raw_bytes = path.read_bytes()
            resp = ingestion_svc.ingest_upload(
                db,
                filename=path.name,
                content_type=content_type,
                raw_bytes=raw_bytes,
                strategy="recursive",
            )
            msg = f"{resp.status} ({resp.num_chunks} chunks)"
            if resp.message:
                msg += f" — {resp.message}"
            results[path.name] = msg
            print(f"  ✓ {path.name}: {msg}")
        except Exception as exc:
            results[path.name] = f"error: {exc}"
            print(f"  ✗ {path.name}: {exc}")
    return results


def _seed_offline(files: list, results: dict) -> dict:
    """Offline in-memory ingestion — loads, chunks, embeds, upserts to in-memory store."""
    import uuid as _uuid
    from app.chunking import get_chunker
    from app.ingestion.detect import detect_doc_type
    from app.ingestion.loaders import get_loader
    from app.services.embeddings import get_embedding_client
    from app.services.vector_store import get_vector_store

    chunker = get_chunker("recursive")
    embedding_client = get_embedding_client()
    vector_store = get_vector_store()

    for path in files:
        if not path.exists():
            results[path.name] = "missing"
            print(f"  - {path.name}: missing")
            continue
        content_type = _get_content_type(path.name)
        try:
            doc_type = detect_doc_type(path.name, content_type)
            raw_bytes = path.read_bytes()
            loader = get_loader(doc_type)
            sections = loader.load(raw_bytes, path.name)
            chunk_pieces = chunker.chunk(sections)
            if not chunk_pieces:
                results[path.name] = "no chunks"
                print(f"  - {path.name}: no chunks produced")
                continue
            texts = [cp.text for cp in chunk_pieces]
            embedding_result = embedding_client.embed(texts)
            vectors = embedding_result.vectors
            doc_id = str(_uuid.uuid4())
            chunk_ids = [str(_uuid.uuid4()) for _ in chunk_pieces]
            payloads = [
                {
                    "document_id": doc_id,
                    "chunk_id": cid,
                    "source_file": path.name,
                    "page_number": cp.page_number,
                    "section_title": cp.section_title,
                    "text": cp.text,
                }
                for cid, cp in zip(chunk_ids, chunk_pieces)
            ]
            vector_store.upsert(chunk_ids, vectors, payloads)
            msg = f"offline: {len(chunk_pieces)} chunks indexed in-memory"
            results[path.name] = msg
            print(f"  ✓ {path.name}: {msg}")
        except Exception as exc:
            results[path.name] = f"error: {exc}"
            print(f"  ✗ {path.name}: {exc}")
    return results


def main() -> None:
    print(f"\n=== Acme Corp Sample Data Seeder ===")
    print(f"Corpus directory: {_SAMPLE_DATA_DIR}\n")

    # Try to get a DB session
    db = None
    try:
        from app.db.session import SessionLocal
        import sqlalchemy

        db = SessionLocal()
        db.execute(sqlalchemy.text("SELECT 1"))
        print("Database: connected\n")
    except Exception as e:
        print(f"Database: unavailable ({e})")
        print("Running in offline mode — in-memory vector store only.\n")

    try:
        results = seed(db)
        print(f"\n=== Seeding complete: {len(results)} files processed ===")
        for fn, status in results.items():
            print(f"  {fn}: {status}")
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
