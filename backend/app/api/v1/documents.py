"""/v1/ingest and /v1/documents."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.document import Document
from app.schemas.document import DocumentOut, IngestResponse
from app.services.ingestion_service import get_ingestion_service

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(require_admin)])
async def ingest(
    file: UploadFile = File(...),
    strategy: str | None = Query(None, description="fixed|recursive|semantic"),
    db: Session = Depends(get_db),
):
    # Read at most the cap (+1 byte to detect overflow) so an oversized upload
    # never gets fully buffered into memory.
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_bytes} byte upload limit.",
        )
    service = get_ingestion_service()
    try:
        return service.ingest_upload(
            db,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            raw_bytes=raw,
            strategy=strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    docs = db.scalars(select(Document).order_by(Document.ingested_at.desc())).all()
    return list(docs)


@router.delete("/documents", dependencies=[Depends(require_admin)])
def clear_documents(db: Session = Depends(get_db)):
    """Delete the entire corpus: all documents, chunks, and vectors."""
    service = get_ingestion_service()
    count = service.delete_all_documents(db)
    return {"deleted_count": count}


@router.delete("/documents/{document_id}", dependencies=[Depends(require_admin)])
def delete_document(document_id: str, db: Session = Depends(get_db)):
    service = get_ingestion_service()
    ok = service.delete_document(db, document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": document_id}
