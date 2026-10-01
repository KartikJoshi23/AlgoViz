"""
Application entry point
=======================

`create_app()` builds the FastAPI app (used by uvicorn, tests, and the OpenAPI
export script). Run with `uvicorn algoviz.main:app --no-proxy-headers`: the
app resolves forwarded client addresses itself, trusting only
`TRUSTED_PROXIES`, so the same rule holds under any server and in tests.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from algoviz import __version__
from algoviz.api.alerts import router as alerts_router
from algoviz.api.analytics import router as analytics_router
from algoviz.api.auth import router as auth_router
from algoviz.api.market import router as market_router
from algoviz.api.strategies import router as strategies_router
from algoviz.api.system import router as system_router
from algoviz.api.system import system_stats
from algoviz.config import settings
from algoviz.core.logging import configure_logging
from algoviz.core.looplag import loop_lag
from algoviz.core.metrics import build_registry
from algoviz.core.middleware import (
    ObservabilityMiddleware,
    RateLimitMiddleware,
    install_request_id_filter,
)
from algoviz.core.problems import install_problem_handlers
from algoviz.core.time import utcnow
from algoviz.core.users import ensure_default_user
from algoviz.db import async_session, close_db, init_db
from algoviz.market.service import market_service
from algoviz.schemas.rest import (
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
    RootResponse,
)
from algoviz.ws.hub import ws_manager

logger = logging.getLogger("algoviz")
_started_at = time.monotonic()
_db_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _db_ready
    configure_logging(settings.LOG_LEVEL, settings.LOG_JSON)
    install_request_id_filter()
    logger.info(
        "AlgoViz %s starting (env=%s, source=%s, symbols=%s)",
        __version__,
        settings.ENVIRONMENT,
        settings.DATA_SOURCE,
        ",".join(settings.SYMBOLS),
    )
    await init_db()
    await ensure_default_user(async_session)
    _db_ready = True
    if settings.MARKET_AUTOSTART:
        await market_service.start()
    await loop_lag.start()  # measures serving, not the one-off startup work above
    try:
        yield
    finally:
        logger.info("shutting down")
        await ws_manager.close_all()
        await market_service.stop()
        await loop_lag.stop()
        await close_db()
        _db_ready = False


def readiness() -> ReadinessResponse:
    """Checks behind `/health/ready`: schema migrated, every book synced and fresh, loop responsive."""
    checks: dict[str, bool] = {"database": _db_ready}
    detail: dict[str, str] = {}
    if settings.MARKET_AUTOSTART:
        for sym in settings.SYMBOLS:
            engine = market_service.get(sym)
            payload = engine.stats() if engine else None
            ok = bool(
                payload and payload["book"]["state"] == "synced" and payload["status"] != "stale"
            )
            checks[f"market:{sym}"] = ok
            if not ok:
                detail[f"market:{sym}"] = (
                    "engine not running"
                    if payload is None
                    else f"book {payload['book']['state']}, feed {payload['status']}"
                )
    p99 = loop_lag.p99_ms()
    checks["event_loop"] = p99 is None or p99 <= settings.LOOP_LAG_DEGRADED_MS
    if not checks["event_loop"]:
        detail["event_loop"] = f"lag p99 {p99:.0f} ms > {settings.LOOP_LAG_DEGRADED_MS:.0f} ms"
    return ReadinessResponse(ready=all(checks.values()), checks=checks, detail=detail)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description=(
            "Real-time market-microstructure intelligence: streaming features, "
            "order-book analytics, calibrated ML signals, alerts and backtesting."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    install_problem_handlers(app)

    # Middleware order: last added runs first. CORS must be outermost so
    # preflight and error responses still carry CORS headers; the client
    # address is resolved (trusted proxies only) before the rate limiter keys on it.
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.RATE_LIMIT_RPM,
        writes_per_minute=settings.RATE_LIMIT_WRITE_RPM,
        backtests_per_minute=settings.RATE_LIMIT_BACKTEST_RPM,
    )
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.TRUSTED_PROXIES)
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX,
        allow_credentials=False,  # bearer tokens, never cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID", "X-Response-Time", "Retry-After"],
    )
    metrics_registry = build_registry(system_stats)
    origin_pattern = re.compile(settings.CORS_ORIGIN_REGEX) if settings.CORS_ORIGIN_REGEX else None

    def origin_allowed(origin: str) -> bool:
        if origin in settings.ws_origins:
            return True
        return settings.WS_ALLOWED_ORIGINS is None and bool(
            origin_pattern and origin_pattern.fullmatch(origin)
        )

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health() -> HealthResponse:
        connected = market_service.is_connected
        p99 = loop_lag.p99_ms()
        healthy = (connected or not settings.MARKET_AUTOSTART) and (
            p99 is None or p99 <= settings.LOOP_LAG_DEGRADED_MS
        )
        return HealthResponse(
            status="ok" if healthy else "degraded",
            version=__version__,
            environment=settings.ENVIRONMENT,
            uptime_seconds=round(time.monotonic() - _started_at, 1),
            data_source=settings.DATA_SOURCE,
            symbols=settings.SYMBOLS,
            market_connected=connected,
            ws_clients=ws_manager.active_count,
            loop_lag_p99_ms=round(p99, 2) if p99 is not None else None,
            timestamp=utcnow(),
        )

    @app.get("/health/live", response_model=LivenessResponse, tags=["System"])
    async def health_live() -> LivenessResponse:
        return LivenessResponse()

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        tags=["System"],
        responses={503: {"model": ReadinessResponse, "description": "Not ready"}},
    )
    async def health_ready() -> ReadinessResponse | JSONResponse:
        r = readiness()
        if r.ready:
            return r
        return JSONResponse(status_code=503, content=r.model_dump(mode="json"))

    @app.get("/metrics", tags=["System"], summary="Prometheus metrics", response_class=Response)
    async def metrics() -> Response:
        return Response(generate_latest(metrics_registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/", response_model=RootResponse, tags=["System"])
    async def root() -> RootResponse:
        return RootResponse(
            app=settings.APP_NAME,
            version=__version__,
            docs="/docs",
            health="/health",
            api="/api/v1",
        )

    for r in (
        auth_router,
        market_router,
        strategies_router,
        alerts_router,
        analytics_router,
        system_router,
    ):
        app.include_router(r, prefix="/api/v1")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, symbol: str | None = None) -> None:
        origin = websocket.headers.get("origin")
        if origin is not None and not origin_allowed(origin):
            logger.warning("ws refused: origin %s is not allowed", origin)
            await websocket.close(code=1008)  # before accept: the handshake gets a 403
            return
        if ws_manager.active_count >= settings.WS_MAX_CLIENTS:
            await websocket.accept()
            await websocket.close(code=1013, reason="server full, try again later")
            return
        await ws_manager.connect(websocket, symbol)
        try:
            while True:
                text = await websocket.receive_text()
                await ws_manager.handle_client_message(websocket, text)
        except WebSocketDisconnect:
            pass
        finally:
            await ws_manager.disconnect(websocket)

    return app


app = create_app()
