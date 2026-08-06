"""Tests for settings resolution, in particular the DATABASE_URL override.

Managed Postgres providers (Neon, Supabase, Railway) issue a single connection
string instead of discrete host/port/user/password parts, and that string
usually carries query args such as ?sslmode=require. These tests pin the
precedence rule and the driver-scheme rewrite that makes such a string usable
with psycopg 3.

Fully offline: nothing here opens a connection.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    """Build Settings without reading the developer's local .env file."""
    return Settings(_env_file=None, **overrides)


# --------------------------------------------------------------------------- #
# Default assembly from discrete parts                                         #
# --------------------------------------------------------------------------- #

def test_database_url_assembled_from_parts_when_no_override():
    s = _settings(
        postgres_user="rag",
        postgres_password="rag",
        postgres_host="postgres",
        postgres_port=5432,
        postgres_db="rag",
    )
    assert s.database_url == "postgresql+psycopg://rag:rag@postgres:5432/rag"


# --------------------------------------------------------------------------- #
# DATABASE_URL override                                                        #
# --------------------------------------------------------------------------- #

def test_override_takes_precedence_over_discrete_parts():
    s = _settings(
        postgres_host="postgres",
        postgres_user="rag",
        database_url_override="postgresql://neo:pw@ep-x.neon.tech/main",
    )
    assert s.database_url == "postgresql+psycopg://neo:pw@ep-x.neon.tech/main"
    assert "postgres:5432" not in s.database_url


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://u:p@host/db",
        "postgres://u:p@host/db",
    ],
)
def test_bare_schemes_are_rewritten_to_psycopg3(raw):
    # SQLAlchemy maps both bare schemes to psycopg2, which is not installed;
    # without the rewrite, engine creation raises ModuleNotFoundError.
    # Asserted as a full equality, not startswith(): the fallback URL also
    # starts with postgresql+psycopg://, so a prefix check passes even when the
    # override is ignored entirely.
    assert _settings(database_url_override=raw).database_url == (
        "postgresql+psycopg://u:p@host/db"
    )


def test_query_args_are_preserved():
    # Neon/Supabase require SSL; dropping the query string breaks the connection.
    s = _settings(
        database_url_override="postgresql://u:p@ep-x.neon.tech/main?sslmode=require"
    )
    assert s.database_url.endswith("?sslmode=require")


def test_explicit_psycopg_scheme_is_left_alone():
    raw = "postgresql+psycopg://u:p@host/db"
    assert _settings(database_url_override=raw).database_url == raw


def test_blank_and_whitespace_override_falls_back_to_parts():
    for blank in ("", "   "):
        s = _settings(database_url_override=blank, postgres_host="postgres")
        assert s.database_url == "postgresql+psycopg://rag:rag@postgres:5432/rag"


def test_override_is_read_from_the_DATABASE_URL_env_var(monkeypatch):
    # The field is named database_url_override, so the alias is what makes the
    # conventional DATABASE_URL name work.
    monkeypatch.setenv("DATABASE_URL", "postgresql://envuser:envpw@envhost/envdb")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://envuser:envpw@envhost/envdb"
