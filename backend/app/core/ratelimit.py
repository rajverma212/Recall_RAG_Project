"""Per-IP rate limiting (pure-ASGI middleware).

Guards the public API. The generation routes (``/v1/ask``, ``/v1/ask/stream``)
spend the configured LLM provider's budget on every call, so they get a stricter
per-IP cap than the rest of the API; the liveness ``/health`` probe is never
limited. Built directly on the ``limits`` library with an in-process
moving-window store.

Implemented as pure ASGI (not BaseHTTPMiddleware) so it never buffers the
response body — the SSE ``/ask/stream`` endpoint keeps streaming token-by-token
— while still injecting ``RateLimit-*`` headers on the response start.

Behind a proxy (Railway/Vercel) the client IP is taken from the first hop of
``X-Forwarded-For``. Limits are per-replica (in-process); for shared limits
across replicas, point ``limits`` at Redis/Memcached instead of MemoryStorage.
"""
from __future__ import annotations

import time

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Left-most entry is the originating client; the rest are proxy hops.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "anonymous"


class RateLimitMiddleware:
    """Per-IP limits keyed by route class (LLM-spend endpoints vs. everything else)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._limiter = MovingWindowRateLimiter(MemoryStorage())
        self._default = parse(settings.rate_limit_default)
        self._ask = parse(settings.rate_limit_ask)
        prefix = settings.api_v1_prefix
        # LLM-spend endpoints get the stricter cap.
        self._ask_paths = {f"{prefix}/ask", f"{prefix}/ask/stream"}
        # Liveness probe stays unlimited so platform healthchecks aren't throttled.
        self._exempt = {"/health"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path in self._exempt:
            await self.app(scope, receive, send)
            return

        is_ask = path in self._ask_paths
        limit = self._ask if is_ask else self._default
        bucket = "ask" if is_ask else "default"  # separate counters per class
        ip = _client_ip(Request(scope))

        if not self._limiter.hit(limit, bucket, ip):
            reset, _ = self._limiter.get_window_stats(limit, bucket, ip)
            retry_after = max(1, int(reset - time.time()))
            response = JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {limit}"},
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        reset, remaining = self._limiter.get_window_stats(limit, bucket, ip)
        reset_secs = max(0, int(reset - time.time()))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"ratelimit-limit", str(limit.amount).encode()))
                headers.append((b"ratelimit-remaining", str(remaining).encode()))
                headers.append((b"ratelimit-reset", str(reset_secs).encode()))
            await send(message)

        await self.app(scope, receive, send_with_headers)
