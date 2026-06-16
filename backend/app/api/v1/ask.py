"""POST /v1/ask — grounded answer with citations, verification, confidence."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ask import AskRequest, AskResponse
from app.services.rag_service import get_rag_service

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, db: Session = Depends(get_db)):
    service = get_rag_service()
    if req.stream:
        # Non-streaming clients still get JSON; streaming handled below.
        pass
    return service.ask(db, req)


@router.post("/ask/stream")
def ask_stream(req: AskRequest, db: Session = Depends(get_db)):
    """Server-sent-events stream: token deltas, then a final ``done`` event
    carrying the full AskResponse (citations + confidence)."""
    service = get_rag_service()

    def event_gen():
        for event in service.ask_stream(db, req):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
