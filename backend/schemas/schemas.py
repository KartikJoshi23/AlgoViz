"""
AlgoViz Backend — Pydantic Schemas
====================================

Request/response models for all API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ═════════════════════════════════════════════════════════════════════
# AUTH
# ═════════════════════════════════════════════════════════════════════

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LoginRequest(BaseModel):
    username: str
    password: str


# ═════════════════════════════════════════════════════════════════════
# MARKET DATA
# ═════════════════════════════════════════════════════════════════════

class MarketFeatures(BaseModel):
    """Current market features — the core data contract."""
    symbol: str = "BTCUSDT"
    current_price: float = 0.0
    mid_price: float = 0.0
    spread: float = 0.0
    spread_bps: float = 0.0
    vwap: float = 0.0
    twap: float = 0.0
    imbalance: float = 0.0
    imbalance_pct: float = 0.0
    volatility_bps: float = 0.0
    velocity: float = 0.0
    velocity_baseline: float = 20.0
    buy_pressure: float = 0.5
    price_change: float = 0.0
    price_change_pct: float = 0.0
    price_vs_vwap: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    timestamp: Optional[datetime] = None


class TradeData(BaseModel):
    """Single trade record."""
    price: float
    quantity: float
    is_buyer_maker: bool
    trade_id: int
    timestamp: datetime


class DepthLevel(BaseModel):
    price: float
    quantity: float


class OrderBookData(BaseModel):
    """Order book snapshot."""
    bids: List[DepthLevel] = []
    asks: List[DepthLevel] = []
    best_bid: float = 0.0
    best_ask: float = 0.0
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    timestamp: Optional[datetime] = None


class PriceChartPoint(BaseModel):
    timestamp: datetime
    price: float
    vwap: float
    twap: Optional[float] = None


class SpreadChartPoint(BaseModel):
    timestamp: datetime
    spread_bps: float


class VolatilityChartPoint(BaseModel):
    timestamp: datetime
    volatility_bps: float


# ═════════════════════════════════════════════════════════════════════
# STRATEGIES
# ═════════════════════════════════════════════════════════════════════

class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    strategy_type: str = "rule_based"
    config: Dict[str, Any] = {}


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class StrategyResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: Optional[str]
    strategy_type: str
    config: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BacktestRequest(BaseModel):
    strategy_id: int
    initial_capital: float = 10000.0
    data_points: int = 1000
    commission_bps: float = 1.0
    slippage_bps: float = 0.5


class BacktestResponse(BaseModel):
    id: int
    strategy_id: int
    total_pnl: float
    total_pnl_pct: float
    total_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    initial_capital: float
    final_capital: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ═════════════════════════════════════════════════════════════════════
# ALERTS
# ═════════════════════════════════════════════════════════════════════

class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    alert_type: str
    condition_field: str
    comparison: str  # gt, lt, gte, lte, eq
    threshold: float
    priority: str = "medium"
    message_template: Optional[str] = None
    cooldown_seconds: int = 30
    notify_discord: bool = False
    notify_email: bool = False


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    threshold: Optional[float] = None
    priority: Optional[str] = None
    is_enabled: Optional[bool] = None
    cooldown_seconds: Optional[int] = None


class AlertRuleResponse(BaseModel):
    id: int
    name: str
    alert_type: str
    condition_field: str
    comparison: str
    threshold: float
    priority: str
    is_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertHistoryResponse(BaseModel):
    id: int
    rule_id: int
    priority: str
    message: str
    value: Optional[float]
    threshold: Optional[float]
    acknowledged: bool
    triggered_at: datetime

    model_config = {"from_attributes": True}


# ═════════════════════════════════════════════════════════════════════
# ML / PREDICTIONS
# ═════════════════════════════════════════════════════════════════════

class MLPrediction(BaseModel):
    direction: str = "neutral"  # strong_up, up, neutral, down, strong_down
    confidence: float = 0.5
    predicted_move_bps: float = 0.0
    momentum_score: float = 0.0
    momentum_label: str = "neutral"
    regime: str = "ranging"
    reversal_probability: float = 0.0
    signal_action: str = "HOLD"
    feature_importance: Dict[str, float] = {}
    model_name: Optional[str] = None
    timestamp: Optional[datetime] = None


class MLModelInfo(BaseModel):
    id: int
    name: str
    model_type: str
    version: int
    accuracy: Optional[float]
    f1: Optional[float]
    is_active: bool
    trained_at: datetime

    model_config = {"from_attributes": True}


# ═════════════════════════════════════════════════════════════════════
# INSIGHTS (from rule engine)
# ═════════════════════════════════════════════════════════════════════

class InsightResponse(BaseModel):
    rule_id: int
    priority: str
    priority_emoji: str
    insight: str
    action: str
    how_to_overcome: str
    expected_impact: str
    triggered_at: Optional[datetime] = None


# ═════════════════════════════════════════════════════════════════════
# WEBSOCKET MESSAGES
# ═════════════════════════════════════════════════════════════════════

class WSMessage(BaseModel):
    """Standard WebSocket message envelope."""
    type: str  # features, trade, depth, insight, alert, prediction
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ═════════════════════════════════════════════════════════════════════
# GENERIC RESPONSES
# ═════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    uptime_seconds: float
    connections: Dict[str, Any] = {}


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    has_next: bool
