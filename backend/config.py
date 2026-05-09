"""
AlgoViz Backend — Configuration
================================

Centralized configuration using Pydantic Settings.
All values are loaded from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
from pathlib import Path
import os


# Base directory (backend/)
BASE_DIR = Path(__file__).resolve().parent

# Database file lives alongside backend/
DATABASE_DIR = BASE_DIR / "data"
DATABASE_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    """Application settings — loaded from env vars or .env file."""

    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "AlgoViz"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # ── Server ───────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3002",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:5173",
        # Production deployments
        "https://algoviz.vercel.app",
        "https://algo-viz.vercel.app",
        "https://algoviz.netlify.app",
        "https://algo-viz.netlify.app",
        "https://algoviz-5saw.onrender.com",
    ]

    # ── Database ─────────────────────────────────────────────────────
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATABASE_DIR / 'algoviz.db'}"

    # ── Auth / JWT ───────────────────────────────────────────────────
    SECRET_KEY: str = "algoviz-dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # ── Exchange WebSocket URLs ──────────────────────────────────────
    BINANCE_TRADE_WS: str = "wss://stream.binance.com:9443/ws/btcusdt@trade"
    BINANCE_DEPTH_WS: str = (
        "wss://stream.binance.com:9443/ws/btcusdt@depth10@100ms"
    )
    BINANCE_COMBINED_WS: str = (
        "wss://stream.binance.com:9443/stream?streams="
        "btcusdt@trade/btcusdt@depth10@100ms"
    )

    # ── Market Data Defaults ─────────────────────────────────────────
    DEFAULT_SYMBOL: str = "BTCUSDT"
    TRADES_BUFFER_SIZE: int = 1000
    DEPTH_BUFFER_SIZE: int = 100
    PRICE_HISTORY_SIZE: int = 200
    SPREAD_HISTORY_SIZE: int = 100
    VOLATILITY_HISTORY_SIZE: int = 200

    # ── Time Windows (seconds) ───────────────────────────────────────
    VWAP_WINDOW: int = 30
    VELOCITY_WINDOW: int = 3
    VOLATILITY_WINDOW: int = 60
    BUY_PRESSURE_WINDOW: int = 30

    # ── Thresholds ───────────────────────────────────────────────────
    SPREAD_HIGH_BPS: float = 6.0
    SPREAD_LOW_BPS: float = 2.0
    IMBALANCE_STRONG_SELL: float = -0.5
    IMBALANCE_STRONG_BUY: float = 0.5
    VOLATILITY_HIGH_BPS: float = 20.0
    VOLATILITY_LOW_BPS: float = 10.0
    VELOCITY_SPIKE_MULTIPLIER: float = 2.0
    VELOCITY_THIN_MULTIPLIER: float = 0.5
    PRICE_OVERBOUGHT_PCT: float = 0.1
    PRICE_OVERSOLD_PCT: float = -0.1
    DEFAULT_VELOCITY_BASELINE: float = 20.0

    # ── ML Config ────────────────────────────────────────────────────
    ML_PREDICTION_HORIZON: int = 5  # seconds
    ML_MIN_DATA_POINTS: int = 20
    ML_HISTORY_SIZE: int = 500
    ML_MODEL_DIR: str = str(BASE_DIR / "ml_models")

    # ── Alert Config ─────────────────────────────────────────────────
    ALERT_MAX_HISTORY: int = 500
    ALERT_DEFAULT_COOLDOWN: int = 30
    DISCORD_WEBHOOK_URL: Optional[str] = None

    # ── Redis (optional, for Phase 5) ────────────────────────────────
    REDIS_URL: Optional[str] = None

    # ── On-Chain / Foundry (Phase 4) ────────────────────────────────
    ETH_RPC_URL: Optional[str] = None
    FOUNDRY_PROJECT_DIR: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
    }


# Global settings singleton
settings = Settings()
