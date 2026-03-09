"""
AlgoViz Backend — ORM Models
==============================

SQLAlchemy models for all persistent entities.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from database import Base


# ═════════════════════════════════════════════════════════════════════
# USER
# ═════════════════════════════════════════════════════════════════════

class User(Base):
    """Application user (supports future multi-user mode)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    strategies = relationship("Strategy", back_populates="owner", cascade="all, delete")
    alert_rules = relationship("AlertRule", back_populates="owner", cascade="all, delete")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete")


# ═════════════════════════════════════════════════════════════════════
# USER SESSION (for tracking active sessions / preferences)
# ═════════════════════════════════════════════════════════════════════

class UserSession(Base):
    """Tracks user sessions and preferences."""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(500), nullable=False, index=True)
    data_mode = Column(String(20), default="static")  # "static" | "live"
    preferred_symbol = Column(String(20), default="BTCUSDT")
    theme = Column(String(10), default="dark")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="sessions")


# ═════════════════════════════════════════════════════════════════════
# STRATEGY
# ═════════════════════════════════════════════════════════════════════

class Strategy(Base):
    """A user-defined trading strategy with rules and parameters."""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    strategy_type = Column(String(50), default="rule_based")  # rule_based | ml_signal | hybrid
    config = Column(JSON, nullable=False, default=dict)
    # config schema example:
    # {
    #   "rules": [...],
    #   "entry_conditions": {...},
    #   "exit_conditions": {...},
    #   "risk_params": {"stop_loss_pct": 0.5, "take_profit_pct": 1.0, "max_position_size": 1.0}
    # }
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="strategies")
    backtests = relationship("BacktestResult", back_populates="strategy", cascade="all, delete")


# ═════════════════════════════════════════════════════════════════════
# BACKTEST RESULT
# ═════════════════════════════════════════════════════════════════════

class BacktestResult(Base):
    """Persisted backtest results for a strategy."""
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    total_pnl = Column(Float, default=0.0)
    total_pnl_pct = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    max_drawdown_pct = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    initial_capital = Column(Float, default=10000.0)
    final_capital = Column(Float, default=10000.0)
    trades_json = Column(JSON, default=list)  # List of individual trade records
    equity_curve_json = Column(JSON, default=list)  # [(timestamp, equity), ...]
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    strategy = relationship("Strategy", back_populates="backtests")


# ═════════════════════════════════════════════════════════════════════
# ALERT RULE
# ═════════════════════════════════════════════════════════════════════

class AlertRule(Base):
    """User-defined alert rules with custom thresholds."""
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    alert_type = Column(String(50), nullable=False)
    # Types: price_threshold, spread_threshold, volatility_threshold,
    #        imbalance_threshold, velocity_threshold, ml_signal, custom
    condition_field = Column(String(50), nullable=False)  # e.g. "spread_bps"
    comparison = Column(String(10), nullable=False)  # "gt", "lt", "gte", "lte", "eq"
    threshold = Column(Float, nullable=False)
    priority = Column(String(20), default="medium")  # critical, high, medium, low, info
    message_template = Column(Text, nullable=True)
    cooldown_seconds = Column(Integer, default=30)
    is_enabled = Column(Boolean, default=True)
    notify_discord = Column(Boolean, default=False)
    notify_email = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="alert_rules")
    alerts = relationship("AlertHistory", back_populates="rule", cascade="all, delete")


# ═════════════════════════════════════════════════════════════════════
# ALERT HISTORY
# ═════════════════════════════════════════════════════════════════════

class AlertHistory(Base):
    """Record of triggered alerts."""
    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=False)
    priority = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    value = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, nullable=True)
    triggered_at = Column(DateTime, default=datetime.utcnow)

    rule = relationship("AlertRule", back_populates="alerts")

    __table_args__ = (
        Index("ix_alert_history_triggered", "triggered_at"),
    )


# ═════════════════════════════════════════════════════════════════════
# MARKET DATA SNAPSHOT (for persistence & replay)
# ═════════════════════════════════════════════════════════════════════

class MarketSnapshot(Base):
    """Periodic snapshots of market features for historical analysis."""
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(Float, nullable=False)
    mid_price = Column(Float, nullable=True)
    spread_bps = Column(Float, nullable=True)
    vwap = Column(Float, nullable=True)
    imbalance = Column(Float, nullable=True)
    volatility_bps = Column(Float, nullable=True)
    velocity = Column(Float, nullable=True)
    buy_pressure = Column(Float, nullable=True)
    bid_volume = Column(Float, nullable=True)
    ask_volume = Column(Float, nullable=True)
    trade_count = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_market_symbol_ts", "symbol", "timestamp"),
    )


# ═════════════════════════════════════════════════════════════════════
# ML MODEL REGISTRY
# ═════════════════════════════════════════════════════════════════════

class MLModel(Base):
    """Registry of trained ML models and their performance metrics."""
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    model_type = Column(String(50), nullable=False)  # random_forest, xgboost, etc.
    version = Column(Integer, default=1)
    file_path = Column(String(500), nullable=True)
    accuracy = Column(Float, nullable=True)
    precision_score = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1 = Column(Float, nullable=True)
    training_samples = Column(Integer, nullable=True)
    feature_importance = Column(JSON, nullable=True)
    hyperparameters = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    trained_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
