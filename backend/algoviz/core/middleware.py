"""
Middleware
==========

Pure-ASGI implementations (no `BaseHTTPMiddleware`: it buffers bodies, breaks
streaming, and adds a task hop per request).

- `ObservabilityMiddleware` — `X-Request-ID`, `X-Response-Time`, slow-request log,
  request id attached to log records via a contextvar.
- `RateLimitMiddleware` — sliding 60-second windows per client with periodic
  pruning: one for every request, stricter ones for writes and for backtest
  submissions. The client is `scope["client"]`, which the proxy-headers
  middleware rewrites only for requests arriving through a trusted proxy.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from contextvars import ContextVar
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

logger = logging.getLogger("algoviz.http")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_EXEMPT_PATHS = frozenset(
    {"/health", "/health/live", "/health/ready", "/docs", "/redoc", "/openapi.json"}
)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def install_request_id_filter() -> None:
    logging.getLogger().addFilter(_RequestIdFilter())


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, slow_ms: float = 1000.0) -> None:
        self.app = app
        self.slow_ms = slow_ms

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                elapsed_ms = (time.perf_counter() - start) * 1000
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                headers.append((b"x-response-time", f"{elapsed_ms:.1f}ms".encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms > self.slow_ms:
                logger.warning(
                    "slow request %s %s → %s in %.1fms",
                    scope.get("method"),
                    scope.get("path"),
                    status_code,
                    elapsed_ms,
                )
            request_id_var.reset(token)


_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_BACKTEST_PATH = re.compile(r"^/api/v1/strategies/\d+/backtest$")


class RateLimitMiddleware:
    """Sliding 60-second windows per client and bucket. WebSocket + health/docs are exempt."""

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 240,
        writes_per_minute: int = 60,
        backtests_per_minute: int = 6,
    ) -> None:
        self.app = app
        self.limits = {
            "all": requests_per_minute,
            "write": writes_per_minute,
            "backtest": backtests_per_minute,
        }
        self._windows: dict[tuple[str, str], deque[float]] = {}
        self._last_prune = time.monotonic()

    @staticmethod
    def _buckets(scope: Scope) -> list[str]:
        method = scope.get("method", "GET")
        buckets = ["all"]
        if method in _WRITE_METHODS:
            buckets.append("write")
            if method == "POST" and _BACKTEST_PATH.match(scope.get("path", "")):
                buckets.append("backtest")
        return buckets

    def _client_key(self, scope: Scope) -> str:
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _prune(self, now: float) -> None:
        if now - self._last_prune < 60:
            return
        self._last_prune = now
        cutoff = now - 60
        for key in [k for k, w in self._windows.items() if not w or w[-1] < cutoff]:
            del self._windows[key]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        self._prune(now)
        client = self._client_key(scope)
        cutoff = now - 60
        windows = []
        for bucket in self._buckets(scope):
            window = self._windows.setdefault((bucket, client), deque())
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= self.limits[bucket]:
                await self._reject(scope, send, bucket, max(1, int(60 - (now - window[0]))))
                return
            windows.append(window)
        for window in windows:
            window.append(now)
        await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, send: Send, bucket: str, retry_after: int) -> None:
        what = {"all": "requests", "write": "changes", "backtest": "backtest submissions"}[bucket]
        problem = {
            "type": "about:blank",
            "title": "Too Many Requests",
            "status": 429,
            "detail": f"Rate limit exceeded: at most {self.limits[bucket]} {what} a minute",
            "instance": scope.get("path"),
            "request_id": request_id_var.get(),
        }
        body = json.dumps(problem).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(retry_after).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
