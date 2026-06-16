"""GET /v1/evaluations — list evaluation runs and per-run detail."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evaluation import EvaluationRun
from app.schemas.analytics import EvaluationRunOut

router = APIRouter()


@router.get("/evaluations", response_model=list[EvaluationRunOut])
def list_evaluations(db: Session = Depends(get_db)):
    runs = db.scalars(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc())
    ).all()
    return list(runs)


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
