"""
AlgoViz Backend — Main Application
=====================================

FastAPI entry point with lifespan events, CORS, routing, and WebSocket.
"""

import logging
import time
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("algoviz")

# ── Startup time tracking ─────────────────────────────────────────
_start_time = time.time()

# ── Safe imports (catch any import failures) ──────────────────────
try:
    from database import init_db, close_db
    _db_available = True
except Exception as e:
    logger.error(f"Database import failed: {e}")
    _db_available = False
    async def init_db(): pass
    async def close_db(): pass

try:
    from services.market_data import market_service
    _market_available = True
except Exception as e:
    logger.error(f"Market data import failed: {e}")
    _market_available = False
    class _DummyMarket:
        is_connected = False
        async def start(self): pass
        async def stop(self): pass
        def get_features(self): return type('F', (), {'to_dict': lambda self: {}})()
        def get_trades(self, limit=50): return []
        def get_order_book(self): return {"bids": [], "asks": []}
        def get_stats(self): return {"connected": False, "status": "unavailable"}
    market_service = _DummyMarket()

try:
    from ws.hub import ws_manager
    _ws_available = True
except Exception as e:
    logger.error(f"WebSocket hub import failed: {e}")
    _ws_available = False
    class _DummyWS:
        active_count = 0
        async def connect(self, ws): pass
        async def disconnect(self, ws): pass
    ws_manager = _DummyWS()

# API Routers (safe imports)
_routers = []
for module_name, router_name in [
    ("api.market", "router"),
    ("api.strategies", "router"),
    ("api.alerts", "router"),
    ("api.analytics", "router"),
    ("api.auth", "router"),
]:
    try:
        mod = __import__(module_name, fromlist=[router_name])
        _routers.append((module_name, getattr(mod, router_name)))
    except Exception as e:
        logger.error(f"Router import failed ({module_name}): {e}")


# ── Lifespan ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup → yield → shutdown."""
    logger.info("═" * 60)
    logger.info("  AlgoViz Backend Starting...")
    logger.info(f"  Version: {settings.APP_VERSION}")
    logger.info(f"  Environment: {settings.ENVIRONMENT}")
    logger.info(f"  Python: {sys.version}")
    logger.info("═" * 60)

    try:
        await init_db()
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"Database init failed: {e}")

    try:
        await market_service.start()
        logger.info("✓ Market data service started")
    except Exception as e:
        logger.error(f"Market service start failed: {e}")

    yield  # Application runs here

    # Shutdown
    logger.info("Shutting down...")
    try:
        await market_service.stop()
    except Exception:
        pass
    try:
        await close_db()
    except Exception:
        pass
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

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for production reliability
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Production Middleware (safe) ──────────────────────────────────
try:
    from core.middleware import RequestIdMiddleware, TimingMiddleware, RateLimitMiddleware
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=120)
    logger.info("✓ Production middleware loaded")
except Exception as e:
    logger.warning(f"Middleware load failed (non-critical): {e}")


# ── API Routes ────────────────────────────────────────────────────
for module_name, router in _routers:
    try:
        app.include_router(router, prefix="/api/v1")
    except Exception as e:
        logger.error(f"Router registration failed ({module_name}): {e}")


# ── WebSocket Endpoint ────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time data streaming to frontend."""
    await ws_manager.connect(websocket)
    try:
        while True:
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
        "python": sys.version,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "market_connected": market_service.is_connected,
        "ws_clients": ws_manager.active_count,
        "db_available": _db_available,
        "market_available": _market_available,
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
