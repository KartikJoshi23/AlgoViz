"""
WebSocket message schemas
=========================

Every frame the server sends is one of `ServerMessage` (discriminated on
`type`); every frame a client sends is one of `ClientMessage` (discriminated
on `op`). Both unions are exposed through `GET /api/v1/ws/schema` so they
land in the OpenAPI document and the frontend's generated TypeScript.

Channels a client may subscribe to: see `CHANNELS`. `book` is opt-in because
it is the heaviest stream; everything else is on by default.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

Channel = Literal[
    "features",
    "book",
    "trades",
    "bars",
    "regime",
    "prediction",
    "signals",
    "alerts",
    "backtests",
    "status",
]
CHANNELS: tuple[Channel, ...] = (
    "features", "book", "trades", "bars", "regime", "prediction", "signals", "alerts",
    "backtests", "status",
)  # fmt: skip
DEFAULT_CHANNELS: frozenset[str] = frozenset(CHANNELS) - {"book"}

# High-rate channels use latest-wins delivery; the rest are reliable FIFO.
LATEST_WINS_CHANNELS: frozenset[str] = frozenset({"features", "book"})


# ═════════════════════════════════════════════════════════════════════
# Payloads
# ═════════════════════════════════════════════════════════════════════


class FeaturesPayload(BaseModel):
    symbol: str
    ts_ms: int
    source: str
    warmed_up: bool
    last_price: float | None
    mid: float | None
    microprice: float | None
    microprice_dev_bps: float | None
    vwap: float | None
    twap: float | None
    price_vs_vwap_bps: float | None
    session_change_pct: float | None
    best_bid: float | None
    best_ask: float | None
    bid_qty: float | None
    ask_qty: float | None
    spread_bps: float | None
    imbalance_l1: float | None
    imbalance_w: float | None
    liquidity_5bps: float | None
    liquidity_10bps: float | None
    liquidity_25bps: float | None
    book_slope_bid: float | None
    book_slope_ask: float | None
    ofi_1s: float
    ofi_5s: float
    ofi_30s: float
    velocity: float
    velocity_baseline: float | None
    buy_pressure: float | None
    volume_30s: float
    trade_count_30s: int
    volatility_bps: float | None
    spread_z: float | None
    velocity_z: float | None
    vol_z: float | None
    ofi_z: float | None
    imbalance_z: float | None
    liquidity_z: float | None
    regime: str | None  # volatility state
    regime_direction: float | None
    regime_source: str | None
    trend: str | None
    p_up: float | None = None
    p_down: float | None = None


PriceLevel = Annotated[list[float], Field(min_length=2, max_length=2)]  # [price, qty]


class DepthProfile(BaseModel):
    """Cumulative depth per bin from mid outward (see `LocalOrderBook.depth_profile`)."""

    band_bps: float
    bins: int  # per side
    bids: list[float]  # index 0 = nearest bin
    asks: list[float]


class BookPayload(BaseModel):
    symbol: str
    ts_ms: int
    bids: list[PriceLevel]  # best → worse
    asks: list[PriceLevel]
    profile: DepthProfile | None = None
    mid: float
    microprice: float
    spread_bps: float
    imbalance_l1: float
    imbalance_w: float
    ofi_1s: float
    liquidity_10bps: float
    levels: int
    update_id: int


class TradePayload(BaseModel):
    ts_ms: int
    price: float
    qty: float
    side: Literal["buy", "sell"]
    trade_id: int


class BarRows(BaseModel):
    columns: list[str]
    rows: list[list[float | None]]


class RegimePayload(BaseModel):
    """The volatility state (HMM) and, separately, the trend (drift t-statistic)."""

    symbol: str
    label: Literal["calm", "normal", "elevated", "extreme"]
    direction: float
    trend: Literal["down", "flat", "up"]
    trend_t: float
    probs: dict[str, float]
    source: str
    model_version: int
    bars_seen: int


class DriftSummary(BaseModel):
    status: Literal["no_data", "edge", "no_edge", "decayed"]
    n: int
    n_required: int
    total_resolved: int
    hit_rate: float | None = None
    prior_hit_rate: float | None = None  # always calling the prior's most likely class
    directional_hit_rate: float | None = None
    log_loss: float | None = None
    prior_log_loss: float | None = None
    edge_vs_prior: float | None = None
    trailing_prior_log_loss: float | None = None  # the outcomes resolved before each prediction
    edge_vs_trailing_prior: float | None = None
    brier: float | None = None
    train_log_loss: float | None = None
    train_prior_log_loss: float | None = None
    realised_class_mix: dict[str, float] | None = None
    mean_abs_move_bps: float | None = None


class PredictionPayload(BaseModel):
    symbol: str
    ts_ms: int
    status: Literal["warming_up", "ready", "error"]
    horizon_s: int
    barrier_bps: float
    p_up: float | None
    p_down: float | None
    p_flat: float | None
    predicted_class: Literal["up", "down", "flat"] | None
    confidence: float | None
    signal: Literal["long", "short", "flat"]
    model_version: int
    calibration: str | None
    samples: int
    samples_required: int
    pending_labels: int
    training: bool
    drift: DriftSummary
    timestamp: str


class ActiveSignalPayload(BaseModel):
    rule_id: str
    name: str
    priority: Literal["high", "medium", "low"]
    message: str
    action: str
    impact: str
    tags: list[str]
    activated_at_ms: int
    seconds_active: float
    values: dict[str, Any]


class SignalTransitionPayload(ActiveSignalPayload):
    ts_ms: int
    kind: Literal["activated", "deactivated"]
    duration_s: float | None


class SignalsPayload(BaseModel):
    symbol: str
    transitions: list[SignalTransitionPayload]
    active: list[ActiveSignalPayload]


class BacktestProgressPayload(BaseModel):
    backtest_id: int
    status: Literal["queued", "loading", "running", "completed", "failed"]
    done: int
    total: int
    data_source: str | None = None
    metrics: dict[str, Any] | None = None
    error: str | None = None


class AlertPayload(BaseModel):
    id: int
    rule_id: int
    rule_name: str
    symbol: str
    priority: str
    message: str
    field: str
    value: float | None
    threshold: float | None
    triggered_at: str


class StatusPayload(BaseModel):
    symbol: str
    status: str
    detail: str = ""
    source: str


class HelloPayload(BaseModel):
    version: str
    symbols: list[str]
    default_symbol: str
    source: str
    time_scale: float
    channels: list[str]
    subscribed: list[str]
    bar_columns: list[str]
    server_time_ms: int


class HeatColumn(BaseModel):
    """One second of the liquidity heatmap: the depth profile then, and the prints since the last one."""

    ts_ms: int
    mid: float
    profile: DepthProfile
    buy_qty: float
    buy_notional: float
    sell_qty: float
    sell_notional: float


class SnapshotPayload(BaseModel):
    symbol: str
    features: FeaturesPayload
    book: BookPayload | None
    bars: BarRows
    trades: list[TradePayload]
    regime: RegimePayload
    signals: list[ActiveSignalPayload]
    prediction: PredictionPayload | None
    source_status: StatusPayload
    # the last few minutes of the heatmap, oldest first, so a new client draws it whole
    heat: list[HeatColumn] = []


# ═════════════════════════════════════════════════════════════════════
# Server → client
# ═════════════════════════════════════════════════════════════════════


class _Msg(BaseModel):
    ts: int  # server send time, ms
    symbol: str | None = None


class HelloMessage(_Msg):
    type: Literal["hello"]
    data: HelloPayload


class SnapshotMessage(_Msg):
    type: Literal["snapshot"]
    data: SnapshotPayload


class FeaturesMessage(_Msg):
    type: Literal["features"]
    data: FeaturesPayload


class BookMessage(_Msg):
    type: Literal["book"]
    data: BookPayload


class TradesMessage(_Msg):
    type: Literal["trades"]
    data: list[TradePayload]


class BarMessage(_Msg):
    type: Literal["bar"]
    data: BarRows  # exactly one row


class RegimeMessage(_Msg):
    type: Literal["regime"]
    data: RegimePayload


class PredictionMessage(_Msg):
    type: Literal["prediction"]
    data: PredictionPayload


class SignalsMessage(_Msg):
    type: Literal["signals"]
    data: SignalsPayload


class BacktestProgressMessage(_Msg):
    type: Literal["backtest_progress"]
    data: BacktestProgressPayload


class AlertMessage(_Msg):
    type: Literal["alert"]
    data: AlertPayload


class StatusMessage(_Msg):
    type: Literal["status"]
    data: StatusPayload


class SubscribedMessage(_Msg):
    type: Literal["subscribed"]
    data: dict[str, Any]  # {"channels": [...], "symbol": "..."}


class PongMessage(_Msg):
    type: Literal["pong"]
    data: dict[str, Any] = Field(default_factory=dict)


class ErrorMessage(_Msg):
    type: Literal["error"]
    data: dict[str, Any]  # {"message": "..."}


ServerMessage = Annotated[
    HelloMessage
    | SnapshotMessage
    | FeaturesMessage
    | BookMessage
    | TradesMessage
    | BarMessage
    | RegimeMessage
    | PredictionMessage
    | SignalsMessage
    | BacktestProgressMessage
    | AlertMessage
    | StatusMessage
    | SubscribedMessage
    | PongMessage
    | ErrorMessage,
    Field(discriminator="type"),
]


# ═════════════════════════════════════════════════════════════════════
# Client → server
# ═════════════════════════════════════════════════════════════════════


class SubscribeMessage(BaseModel):
    op: Literal["subscribe"]
    channels: list[Channel] | None = None  # None ⇒ keep current set
    symbol: str | None = None  # switch symbol (rings reset client-side on `snapshot`)


class UnsubscribeMessage(BaseModel):
    op: Literal["unsubscribe"]
    channels: list[Channel]


class PingMessage(BaseModel):
    op: Literal["ping"]
    ts: int | None = None


ClientMessage = Annotated[
    SubscribeMessage | UnsubscribeMessage | PingMessage, Field(discriminator="op")
]


class WSSchema(BaseModel):
    """Container returned by `GET /ws/schema` so both unions appear in OpenAPI."""

    server: ServerMessage
    client: ClientMessage
