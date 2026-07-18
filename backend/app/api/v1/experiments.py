"""GET/POST /v1/experiments — experiment tracking + prompt versioning."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.experiment import Experiment, PromptVersion
from app.schemas.analytics import ExperimentOut

router = APIRouter()


class ExperimentCreate(BaseModel):
    name: str
    description: str | None = None
    config: dict = {}


@router.get("/experiments", response_model=list[ExperimentOut])
def list_experiments(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Experiment).order_by(Experiment.created_at.desc())
    ).all()
    return list(rows)


@router.post("/experiments", response_model=ExperimentOut, dependencies=[Depends(require_admin)])
def create_experiment(body: ExperimentCreate, db: Session = Depends(get_db)):
    exp = Experiment(name=body.name, description=body.description, config=body.config)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


@router.get("/prompts")
def list_prompts(db: Session = Depends(get_db)):
    rows = db.scalars(select(PromptVersion).order_by(PromptVersion.created_at)).all()
    return [
        {
            "version": p.version,
            "name": p.name,
            "description": p.description,
            "is_active": p.is_active,
            "system_prompt": p.system_prompt,
        }
        for p in rows
    ]
