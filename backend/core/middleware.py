"""
AlgoViz Backend — Middleware
================================

Production middleware stack:
- Request ID injection for log correlation
- Response time tracking
- Structured JSON logging
"""

import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("algoviz.middleware")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Inject a unique request ID into every request/response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Track and log response times."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"

        # Log slow requests
        if duration_ms > 1000:
            logger.warning(
                "Slow request: %s %s took %.1fms",
                request.method,
                request.url.path,
                duration_ms,
            )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter per client IP."""

    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.rpm = requests_per_minute
        self._clients: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for WebSocket and health checks
        if request.url.path in ("/ws", "/health", "/docs", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old entries
        window = self._clients.get(client_ip, [])
        window = [t for t in window if now - t < 60]

        if len(window) >= self.rpm:
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=429,
                headers={"Content-Type": "application/json", "Retry-After": "60"},
            )

        window.append(now)
        self._clients[client_ip] = window

        return await call_next(request)
