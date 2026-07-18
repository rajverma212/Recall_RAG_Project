"""Shared FastAPI route dependencies."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import settings

# Header carrying the admin key on destructive/expensive requests.
ADMIN_HEADER = "X-Admin-Key"


def require_admin(x_admin_key: str | None = Header(default=None, alias=ADMIN_HEADER)) -> None:
    """Gate destructive/expensive routes behind an optional admin key.

    No-op when ``settings.admin_api_key`` is unset (the default): the demo stays
    fully open so anyone can browse and ask without signing in. When the key
    *is* configured, every guarded route requires a matching ``X-Admin-Key``
    header and otherwise returns 401 — locking the app down without a login flow.
    """
    expected = settings.admin_api_key
    if not expected:
        return
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin key required for this operation.",
            headers={"WWW-Authenticate": ADMIN_HEADER},
        )
