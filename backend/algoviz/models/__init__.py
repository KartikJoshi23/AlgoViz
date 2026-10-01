"""
ORM models
==========

SQLAlchemy 2.0 typed-declarative models. All datetimes are aware UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from algoviz.core.time import utcnow
from algoviz.db import Base
from algoviz.db.types import UTCDateTime


class _Timestamped:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


# ═════════════════════════════════════════════════════════════════════
# Users
# ═════════════════════════════════════════════════════════════════════


class User(_Timestamped, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    strategies: Mapped[list[Strategy]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    alert_rules: Mapped[list[AlertRule]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


# ═════════════════════════════════════════════════════════════════════
# Strategies & backtests
# ═════════════════════════════════════════════════════════════════════


class Strategy(_Timestamped, Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # rule_based | ml_signal | hybrid
    strategy_type: Mapped[str] = mapped_column(String(50), default="rule_based", nullable=False)
    # Declarative strategy spec — see backtest/strategy.py (Stage C)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner: Mapped[User] = relationship(back_populates="strategies")
    backtests: Mapped[list[BacktestResult]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT", nullable=False)
    data_source: Mapped[str] = mapped_column(String(20), default="history", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)

    initial_capital: Mapped[float] = mapped_column(Float, default=10_000.0, nullable=False)
    final_capital: Mapped[float] = mapped_column(Float, default=10_000.0, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sortino_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exposure_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    commission_bps: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    slippage_bps: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    trades_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    equity_curve_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    end_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    strategy: Mapped[Strategy] = relationship(back_populates="backtests")


# ═════════════════════════════════════════════════════════════════════
# Alerts
# ═════════════════════════════════════════════════════════════════════


class AlertRule(_Timestamped, Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT", nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), default="threshold", nullable=False)
    condition_field: Mapped[str] = mapped_column(String(50), nullable=False)
    comparison: Mapped[str] = mapped_column(String(10), nullable=False)  # gt gte lt lte eq
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    message_template: Mapped[str | None] = mapped_column(Text)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_discord: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_fired_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    owner: Mapped[User] = relationship(back_populates="alert_rules")
    history: Mapped[list[AlertHistory]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )


class AlertHistory(Base):
    __tablename__ = "alert_history"
    __table_args__ = (Index("ix_alert_history_triggered", "triggered_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    triggered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    rule: Mapped[AlertRule] = relationship(back_populates="history")


# ═════════════════════════════════════════════════════════════════════
# Market bars (1 Hz snapshots) — the shared substrate (Stage B)
# ═════════════════════════════════════════════════════════════════════


class MarketSnapshot(Base):
    """One row per 1-second bar per symbol. Features + future mid → ML training set."""

    __tablename__ = "market_snapshots"
    __table_args__ = (Index("ix_market_symbol_ts", "symbol", "timestamp", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="live", nullable=False)

    # Bar
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)  # mid at close
    last_price: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    buy_volume: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trade_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Book / microstructure at close
    spread_bps: Mapped[float | None] = mapped_column(Float)
    microprice: Mapped[float | None] = mapped_column(Float)
    imbalance: Mapped[float | None] = mapped_column(Float)
    imbalance_w: Mapped[float | None] = mapped_column(Float)
    ofi: Mapped[float | None] = mapped_column(Float)
    liquidity_5bps: Mapped[float | None] = mapped_column(Float)
    liquidity_10bps: Mapped[float | None] = mapped_column(Float)
    book_slope: Mapped[float | None] = mapped_column(Float)
    vwap: Mapped[float | None] = mapped_column(Float)
    velocity: Mapped[float | None] = mapped_column(Float)
    buy_pressure: Mapped[float | None] = mapped_column(Float)
    volatility_bps: Mapped[float | None] = mapped_column(Float)

    # z-scores & regime
    spread_z: Mapped[float | None] = mapped_column(Float)
    velocity_z: Mapped[float | None] = mapped_column(Float)
    vol_z: Mapped[float | None] = mapped_column(Float)
    ofi_z: Mapped[float | None] = mapped_column(Float)
    imbalance_z: Mapped[float | None] = mapped_column(Float)
    regime: Mapped[str | None] = mapped_column(String(20))  # volatility state
    trend: Mapped[str | None] = mapped_column(String(8))

    # Anything else the engine wants to persist without a migration
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)


# ═════════════════════════════════════════════════════════════════════
# ML registry & predictions (Stage C)
# ═════════════════════════════════════════════════════════════════════


class MLModel(Base):
    __tablename__ = "ml_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500))
    training_samples: Mapped[int | None] = mapped_column(Integer)
    horizon_s: Mapped[int | None] = mapped_column(Integer)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # per-fold OOS metrics
    feature_names: Mapped[list[str] | None] = mapped_column(JSON)
    feature_importance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    hyperparameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Prediction(Base):
    """Every 1 Hz prediction, resolved later against realised mid → drift monitor."""

    __tablename__ = "predictions"
    __table_args__ = (Index("ix_predictions_symbol_ts", "symbol", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("ml_models.id", ondelete="SET NULL"))
    horizon_s: Mapped[int] = mapped_column(Integer, nullable=False)
    mid_at_prediction: Mapped[float] = mapped_column(Float, nullable=False)
    p_up: Mapped[float] = mapped_column(Float, nullable=False)
    p_down: Mapped[float] = mapped_column(Float, nullable=False)
    p_flat: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_class: Mapped[str] = mapped_column(String(10), nullable=False)
    # Resolution
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    realised_class: Mapped[str | None] = mapped_column(String(10))
    realised_move_bps: Mapped[float | None] = mapped_column(Float)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


__all__ = [
    "AlertHistory",
    "AlertRule",
    "BacktestResult",
    "MLModel",
    "MarketSnapshot",
    "Prediction",
    "Strategy",
    "User",
]
