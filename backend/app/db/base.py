"""Declarative base + metadata import surface for Alembic / create_all."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models so that Base.metadata is fully populated when this module is
# imported (used by init_db and Alembic autogenerate).
from app.models import document, chunk, query_log, evaluation, experiment  # noqa: E402,F401
