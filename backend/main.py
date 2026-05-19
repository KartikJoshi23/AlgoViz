"""
AlgoViz Backend — Main Application
=====================================

FastAPI entry point with lifespan events, CORS, routing, and WebSocket.
"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db, close_db
from services.market_data import market_service
from ws.hub import ws_manager

# API Routers
from api.market import router as market_router
from api.strategies import router as strategies_router
from api.alerts import router as alerts_router
from api.analytics import router as analytics_router
from api.auth import router as auth_router


# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("algoviz")

# ── Startup time tracking ─────────────────────────────────────────
_start_time = time.time()


# ── Lifespan ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup → yield → shutdown."""
    logger.info("═" * 60)
    logger.info("  AlgoViz Backend Starting...")
    logger.info(f"  Version: {settings.APP_VERSION}")
    logger.info(f"  Environment: {settings.ENVIRONMENT}")
    logger.info("═" * 60)

    # Initialize database
    await init_db()
    logger.info("✓ Database initialized")

    # Start market data service
    await market_service.start()
    logger.info("✓ Market data service started")

    yield  # Application runs here

    # Shutdown
    logger.info("Shutting down...")
    await market_service.stop()
    await close_db()
    logger.info("Shutdown complete")


# ── App ───────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Professional-grade algorithmic trading intelligence platform. "
        "Real-time market data, ML predictions, and on-chain analytics."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Production Middleware (added first = runs last) ───────────────
from core.middleware import RequestIdMiddleware, TimingMiddleware, RateLimitMiddleware

app.add_middleware(RequestIdMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=120)

# ── CORS (added last = runs FIRST in Starlette's middleware stack) ─
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.(vercel\.app|netlify\.app|onrender\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Routes ────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(strategies_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")


# ── WebSocket Endpoint ────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time data streaming to frontend."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; listen for client messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


# ── Health Check ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "market_connected": market_service.is_connected,
        "ws_clients": ws_manager.active_count,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint — API info."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1",
    }
