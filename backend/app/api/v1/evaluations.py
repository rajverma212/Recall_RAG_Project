"""Evaluation routes.

GET  /v1/evaluations              — list evaluation runs
GET  /v1/evaluations/status       — current background-run job status
GET  /v1/evaluations/{run_id}     — per-run detail (per-example results)
POST /v1/evaluations/run          — trigger a new evaluation run in the background

The trigger endpoint runs the full EvaluationRunner in a daemon thread with its
own DB session, so the request returns immediately.  A tiny in-memory job
registry (single concurrent run) lets the UI poll for progress.  This is
purely additive — the read endpoints are unchanged.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.evaluation import EvaluationRun
from app.schemas.analytics import EvaluationRunOut

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# In-memory job registry (one run at a time)
# ---------------------------------------------------------------------------

_job_lock = threading.Lock()
_job_state: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "name": None,
    "run_id": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


class RunRequest(BaseModel):
    name: Optional[str] = None
    strategy: Optional[str] = None  # fixed | recursive | semantic
    dense_weight: Optional[float] = None
    sparse_weight: Optional[float] = None


def _run_eval_thread(name: str, config: dict[str, Any]) -> None:
    """Background worker: run the full evaluation and update the job registry."""
    from app.db.session import SessionLocal
    from app.evaluation.runner import EvaluationRunner

    db = SessionLocal()
    try:
        runner = EvaluationRunner(config_overrides=config)
        summary = runner.run(name=name, db=db)
        run_id = summary.get("run_id")
        with _job_lock:
            _job_state.update(
                status="done",
                run_id=run_id,
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=None,
            )
        logger.info(f"Evaluation run {name!r} finished ({run_id})")
    except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
        logger.exception(f"Evaluation run {name!r} failed")
        with _job_lock:
            _job_state.update(
                status="error",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )
    finally:
        try:
            db.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/evaluations", response_model=list[EvaluationRunOut])
def list_evaluations(db: Session = Depends(get_db)):
    runs = db.scalars(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc())
    ).all()
    return list(runs)


@router.get("/evaluations/status")
def evaluation_status():
    """Return the current background evaluation job status (for UI polling)."""
    with _job_lock:
        return dict(_job_state)


@router.post("/evaluations/run", status_code=202, dependencies=[Depends(require_admin)])
def run_evaluation(body: RunRequest | None = None):
    """Kick off a new evaluation run in the background.

    Returns 202 with the job state.  Returns 409 if a run is already in flight.
    """
    body = body or RunRequest()

    with _job_lock:
        if _job_state["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="An evaluation run is already in progress.",
            )

        name = body.name or f"ui-run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        config: dict[str, Any] = {}
        if body.strategy:
            config["chunking_strategy"] = body.strategy
        if body.dense_weight is not None:
            config["dense_weight"] = body.dense_weight
        if body.sparse_weight is not None:
            config["sparse_weight"] = body.sparse_weight

        _job_state.update(
            status="running",
            name=name,
            run_id=None,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            error=None,
        )

    thread = threading.Thread(
        target=_run_eval_thread,
        args=(name, config),
        name=f"eval-run-{uuid.uuid4().hex[:8]}",
        daemon=True,
    )
    thread.start()

    with _job_lock:
        return dict(_job_state)


@router.get("/evaluations/{run_id}")
def get_evaluation(run_id: str, db: Session = Depends(get_db)):
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run": EvaluationRunOut.model_validate(run),
        "results": [
            {
                "example_id": r.example_id,
                "category": r.category,
                "question": r.question,
                "expected_answer": r.expected_answer,
                "predicted_answer": r.predicted_answer,
                "metrics": r.metrics,
                "passed": r.passed,
            }
            for r in run.results
        ],
    }
