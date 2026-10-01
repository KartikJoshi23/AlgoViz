"""
Configuration
=============

Centralised settings loaded from environment variables / `.env`.

Design notes
- Every tunable the engine uses lives here, grouped by concern.
- Rule and alert thresholds are expressed as **z-scores** against adaptive
  baselines, not absolute values.
- Production refuses to start with the development `SECRET_KEY` or without an
  `ADMIN_TOKEN`: reads are public, mutations need that token (or a JWT).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DEV_SECRET_KEY = "algoviz-dev-secret-change-in-production"

DataSource = Literal["live", "replay", "synthetic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "AlgoViz"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False  # structured JSON logs (recommended in production)

    # ── Server ───────────────────────────────────────────────────────
    PORT: int = 8000
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3002",
        "https://algorithmic-viz.vercel.app",
        "https://algoviz.vercel.app",
        "https://algo-viz.vercel.app",
    ]
    # Opt-in pattern for preview deployments (e.g. r"https://algoviz-[a-z0-9-]+\.vercel\.app").
    # None by default: a host-wide wildcard would admit every site on that host.
    CORS_ORIGIN_REGEX: str | None = None
    # Proxies whose X-Forwarded-For is believed (addresses or CIDR networks). The
    # client address keys the rate limiter; believing anyone would let a client
    # choose its own key. Behind Render's proxy: the private ranges.
    TRUSTED_PROXIES: list[str] = ["127.0.0.1", "::1"]
    RATE_LIMIT_RPM: int = 240  # every request, per client
    RATE_LIMIT_WRITE_RPM: int = 60  # POST / PATCH / DELETE, per client
    RATE_LIMIT_BACKTEST_RPM: int = 6  # backtest submissions, per client

    # ── WebSocket ────────────────────────────────────────────────────
    WS_MAX_CLIENTS: int = 200  # beyond this a connection is refused (close 1013, try again later)
    # Browsers always send Origin on a WebSocket handshake; one from elsewhere is
    # refused (close 1008). None → the CORS origins and pattern. A handshake
    # without an Origin (a script, not a browser page) is allowed: reads are public.
    WS_ALLOWED_ORIGINS: list[str] | None = None

    # ── Database ─────────────────────────────────────────────────────
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATA_DIR / 'algoviz.db'}"
    DB_ECHO: bool = False

    # ── Auth / JWT ───────────────────────────────────────────────────
    SECRET_KEY: str = DEV_SECRET_KEY
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    # Reads are public. Mutations (strategies, alert rules, backtests, acknowledgements)
    # need `Authorization: Bearer <ADMIN_TOKEN>` or a user's JWT when this is on;
    # None → on in production, off in development and test (a single local operator).
    MUTATIONS_REQUIRE_AUTH: bool | None = None
    ADMIN_TOKEN: str | None = None  # required (≥ 32 characters) in production
    ALLOW_REGISTRATION: bool | None = None  # None → off in production

    # ── Market data ──────────────────────────────────────────────────
    DATA_SOURCE: DataSource = "live"
    SYMBOLS: list[str] = ["BTCUSDT"]
    SYMBOL_ALLOWLIST: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    MARKET_AUTOSTART: bool = True  # tests set False

    # Ordered host fallbacks. HTTP 451 (geo-block) on one → try the next.
    BINANCE_WS_HOSTS: list[str] = [
        "wss://stream.binance.com:9443",
        "wss://data-stream.binance.vision",
    ]
    BINANCE_REST_HOSTS: list[str] = [
        "https://api.binance.com",
        "https://data-api.binance.vision",
    ]
    REPLAY_FILE: Path | None = None
    REPLAY_SPEED: float = 1.0

    # ── Windows (seconds) ────────────────────────────────────────────
    VWAP_WINDOW: int = 30
    VELOCITY_WINDOW: int = 3
    VOLATILITY_WINDOW: int = 60

    # ── Book payload ─────────────────────────────────────────────────
    # The binned depth profile's half-band adapts to the instrument: it tracks
    # the offset holding BOOK_PROFILE_REACH of the quantity within
    # BOOK_PROFILE_BPS, smoothed, and never below BOOK_PROFILE_MIN_BPS.
    BOOK_PROFILE_BPS: float = 25.0  # maximum half-band (bps)
    BOOK_PROFILE_MIN_BPS: float = 0.5  # minimum half-band (bps)
    BOOK_PROFILE_REACH: float = 0.85  # fraction of in-band depth the band must contain
    BOOK_PROFILE_BINS: int = 64  # bins per side (terrain texture width = 2×)
    # Levels farther than this from mid are dropped from the local book once a
    # second: nothing reads past 25 bps, and a day of diffs would otherwise keep
    # every level price ever touched.
    BOOK_PRUNE_BPS: float = 250.0

    # ── Feed / session continuity ────────────────────────────────────
    FEED_STALE_S: float = 10.0  # no market event for this long ⇒ feed reported "stale"
    # Persisted bars are shown after a restart only if the newest one is at most
    # this old; otherwise charts start fresh instead of splicing across the gap.
    BAR_RESUME_MAX_GAP_S: int = 60

    # ── Baselines (Stage B) ──────────────────────────────────────────
    EWMA_FAST_HALFLIFE_S: float = 60.0
    EWMA_SLOW_HALFLIFE_S: float = 900.0
    ZSCORE_WARMUP_S: int = 120

    # ── ML ───────────────────────────────────────────────────────────
    ML_HORIZON_S: int = 5  # label horizon (bars are 1 s)
    ML_BARRIER_K: float = 1.0  # barrier = K · σ_1s · √horizon
    ML_MIN_BARRIER_BPS: float = 0.5
    ML_MIN_DATA_POINTS: int = 300
    ML_RETRAIN_EVERY_SAMPLES: int = 600
    ML_RETRAIN_MIN_INTERVAL_S: int = 600
    ML_MAX_SAMPLES: int = 20_000
    ML_HISTORY_BARS: int = 7_200  # bars rebuilt from persistence on startup (2 h)
    ML_SIGNAL_THRESHOLD: float = 0.45  # min calibrated probability for a directional signal
    ML_MODEL_DIR: Path = BASE_DIR / "ml_models"
    ML_KEEP_VERSIONS: int = 5
    # Training and HMM fits run in a spawned process with capped threads (0 = half the cores).
    ML_TRAIN_THREADS: int = 0
    ML_TRAIN_TIMEOUT_S: float = 900.0
    ML_TRAIN_RETRY_S: float = 60.0  # back-off after a failed or declined training run
    ML_INFER_TIMEOUT_S: float = 2.0  # a slower prediction is skipped, never queued
    REGIME_FIT_TIMEOUT_S: float = 120.0
    DRIFT_WINDOW: int = 300
    DRIFT_MIN_N: int = 40

    # ── Alerts ───────────────────────────────────────────────────────
    DISCORD_WEBHOOK_URL: str | None = None

    # ── Backtest ─────────────────────────────────────────────────────
    BACKTEST_MIN_BARS: int = 600  # below this, fall back to synthetic history
    BACKTEST_SYNTHETIC_BARS: int = 3_600
    BACKTEST_MAX_BARS: int = 60 * 60 * 24  # one day of 1 s bars (~50 MB in memory)
    BACKTEST_MAX_CONCURRENT: int = 2
    BACKTEST_MAX_QUEUED: int = 8  # running + waiting; beyond this the API answers 429

    # ── Persistence ──────────────────────────────────────────────────
    SNAPSHOT_RETENTION_DAYS: int = 7
    PREDICTION_RETENTION_DAYS: int = 7
    ALERT_HISTORY_RETENTION_DAYS: int = 30

    # ── Health ───────────────────────────────────────────────────────
    LOOP_LAG_DEGRADED_MS: float = 250.0  # event-loop lag p99 above this ⇒ not ready

    # ── Validators ───────────────────────────────────────────────────
    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper_level(cls, v: str) -> str:
        return v.upper()

    @field_validator("DATABASE_URL")
    @classmethod
    def _async_driver(cls, v: str) -> str:
        # Hosts hand out postgres:// or postgresql:// URLs; the engine is async.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v[len(prefix) :]
        return v

    @field_validator("SYMBOLS", "SYMBOL_ALLOWLIST")
    @classmethod
    def _upper_symbols(cls, v: list[str]) -> list[str]:
        return [s.upper() for s in v]

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        if self.ENVIRONMENT == "production" and self.SECRET_KEY == DEV_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is the development default; set a strong SECRET_KEY "
                "before running with ENVIRONMENT=production."
            )
        if self.mutations_require_auth and len(self.ADMIN_TOKEN or "") < 32:
            if self.is_production:
                raise ValueError(
                    "ENVIRONMENT=production requires ADMIN_TOKEN (at least 32 characters): "
                    "mutations are refused without it."
                )
            if self.ADMIN_TOKEN is not None:
                raise ValueError("ADMIN_TOKEN must be at least 32 characters")
        bad = [s for s in self.SYMBOLS if s not in self.SYMBOL_ALLOWLIST]
        if bad:
            raise ValueError(f"SYMBOLS not in SYMBOL_ALLOWLIST: {bad}")
        if self.DATA_SOURCE == "replay" and self.REPLAY_FILE is None:
            raise ValueError("DATA_SOURCE=replay requires REPLAY_FILE")
        # Synthetic / replay runs get their own database and model store unless
        # paths were set explicitly: bars, predictions and trained models from a
        # simulator must never feed the live model or its training history.
        if self.DATA_SOURCE != "live":
            fields = type(self).model_fields
            if self.DATABASE_URL == fields["DATABASE_URL"].default:
                self.DATABASE_URL = (
                    f"sqlite+aiosqlite:///{DATA_DIR / f'algoviz-{self.DATA_SOURCE}.db'}"
                )
            if self.ML_MODEL_DIR == fields["ML_MODEL_DIR"].default:
                self.ML_MODEL_DIR = self.ML_MODEL_DIR / self.DATA_SOURCE
        self.ML_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def mutations_require_auth(self) -> bool:
        return (
            self.is_production
            if self.MUTATIONS_REQUIRE_AUTH is None
            else self.MUTATIONS_REQUIRE_AUTH
        )

    @property
    def registration_open(self) -> bool:
        return (
            not self.is_production if self.ALLOW_REGISTRATION is None else self.ALLOW_REGISTRATION
        )

    @property
    def ws_origins(self) -> list[str]:
        return self.CORS_ORIGINS if self.WS_ALLOWED_ORIGINS is None else self.WS_ALLOWED_ORIGINS

    @property
    def default_symbol(self) -> str:
        return self.SYMBOLS[0]


settings = Settings()

__all__ = ["DEV_SECRET_KEY", "DataSource", "Field", "Settings", "settings"]
