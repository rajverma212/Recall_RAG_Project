"""Create tables and seed the default prompt version. Idempotent."""
from __future__ import annotations

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.generation.prompts import DEFAULT_SYSTEM_PROMPT
from app.models.experiment import PromptVersion

logger = get_logger(__name__)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing = db.scalar(select(PromptVersion).where(PromptVersion.version == "v1"))
        if existing is None:
            db.add(
                PromptVersion(
                    version="v1",
                    name="grounded-default",
                    system_prompt=DEFAULT_SYSTEM_PROMPT,
                    description="Default grounded-generation prompt with strict citations.",
                    is_active=True,
                )
            )
            db.commit()
            logger.info("Seeded default prompt version v1")
