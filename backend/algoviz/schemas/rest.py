"""
REST schemas
============

Request/response models. These are the OpenAPI source of truth from which the
frontend's TypeScript types are generated — every response the API returns
is described here or, for the streamed payloads, in `schemas/ws.py`. The
frontend declares no response shape by hand.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from algoviz.alerts.templates import template_error
from algoviz.backtest.strategy import StrategySpec
from algoviz.market.catalog import validate_condition
from algoviz.schemas.ws import (
    ActiveSignalPayload,
    DriftSummary,
    PredictionPayload,
    RegimePayload,
    SignalTransitionPayload,
)

Comparison = Literal["gt", "gte", "lt", "lte", "eq", "in"]
Priority = Literal["critical", "high", "medium", "low", "info"]
StrategyType = Literal["rule_based", "ml_signal", "hybrid"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ═════════════════════════════════════════════════════════════════════
# Auth
# ═════════════════════════════════════════════════════════════════════


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=72)
    email: str | None = Field(default=None, max_length=255)


class AccessResponse(BaseModel):
    writes_require_auth: bool  # this server gates changes behind a bearer credential
    can_write: bool  # the credential sent with this request (if any) would pass


class LoginRequest(BaseModel):
    username: str
    password: str = Field(max_length=72)


class UserResponse(ORMModel):
    id: int
    username: str
    email: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse


# ═════════════════════════════════════════════════════════════════════
# Strategies & backtests
# ═════════════════════════════════════════════════════════════════════


def _validate_spec(config: dict[str, Any]) -> dict[str, Any]:
    """Validate a strategy config as a StrategySpec and return its canonical JSON form."""
    spec = StrategySpec.model_validate(config)
    return spec.model_dump(mode="json", by_alias=True, exclude_none=True)


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    strategy_type: StrategyType = "rule_based"
    config: dict[str, Any]

    @model_validator(mode="after")
    def _check(self) -> StrategyCreate:
        self.config = _validate_spec(self.config)
        return self


class StrategyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    strategy_type: StrategyType | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _check(self) -> StrategyUpdate:
        if self.config is not None:
            self.config = _validate_spec(self.config)
        return self


class StrategyResponse(ORMModel):
    id: int
    user_id: int
    name: str
    description: str | None
    strategy_type: str
    config: dict[str, Any]
    is_active: bool
    is_public: bool
    created_at: datetime
    updated_at: datetime


class StrategyExample(BaseModel):
    id: str
    config: dict[str, Any]
    description: dict[str, str | None]


class BacktestRequest(BaseModel):
    """`strategy_id` comes from the path — it is not part of the body."""

    symbol: str | None = None
    initial_capital: float = Field(default=10_000.0, gt=0)
    commission_bps: float = Field(default=1.0, ge=0, le=100)
    slippage_bps: float = Field(default=0.5, ge=0, le=100)
    lookback_minutes: int = Field(default=240, ge=5, le=60 * 24)  # ≤ BACKTEST_MAX_BARS of 1 s bars


class BacktestResponse(ORMModel):
    id: int
    strategy_id: int
    symbol: str
    data_source: str
    status: str
    initial_capital: float
    final_capital: float
    total_pnl: float
    total_pnl_pct: float
    total_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    exposure_pct: float
    commission_bps: float
    slippage_bps: float
    start_time: datetime | None
    end_time: datetime | None
    created_at: datetime


class BacktestTrade(BaseModel):
    side: Literal["long", "short"]
    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_bps: float
    costs: float
    hold_s: float
    reason: Literal["stop_loss", "take_profit", "max_hold", "exit_rule", "end_of_data"]


class BacktestDetailResponse(BacktestResponse):
    trades: list[BacktestTrade] = Field(default_factory=list, validation_alias="trades_json")
    # [ts_ms, equity, drawdown_pct] per bar
    equity_curve: list[list[float]] = Field(
        default_factory=list, validation_alias="equity_curve_json"
    )


# ═════════════════════════════════════════════════════════════════════
# Alerts
# ═════════════════════════════════════════════════════════════════════


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    symbol: str | None = None
    alert_type: str = "threshold"
    condition_field: str = Field(min_length=1, max_length=50)
    comparison: Comparison
    threshold: float
    priority: Priority = "medium"
    message_template: str | None = Field(default=None, max_length=500)
    cooldown_seconds: int = Field(default=30, ge=0, le=86_400)
    notify_discord: bool = False
    notify_email: bool = False

    @field_validator("message_template")
    @classmethod
    def _check_template(cls, v: str | None) -> str | None:
        if v is not None and (err := template_error(v)):
            raise ValueError(err)
        return v

    @model_validator(mode="after")
    def _check_condition(self) -> AlertRuleCreate:
        err = validate_condition(self.condition_field, self.comparison)
        if err:
            raise ValueError(err)
        return self


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    condition_field: str | None = Field(default=None, min_length=1, max_length=50)
    comparison: Comparison | None = None
    threshold: float | None = None
    priority: Priority | None = None
    message_template: str | None = Field(default=None, max_length=500)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86_400)
    is_enabled: bool | None = None
    notify_discord: bool | None = None
    notify_email: bool | None = None

    @field_validator("message_template")
    @classmethod
    def _check_template(cls, v: str | None) -> str | None:
        if v is not None and (err := template_error(v)):
            raise ValueError(err)
        return v

    @model_validator(mode="after")
    def _check_condition(self) -> AlertRuleUpdate:
        if self.condition_field is not None and self.comparison is not None:
            err = validate_condition(self.condition_field, self.comparison)
            if err:
                raise ValueError(err)
        elif self.condition_field is not None:
            err = validate_condition(self.condition_field, "gt")
            if err and err.startswith("unknown"):
                raise ValueError(err)
        return self


class AlertRuleResponse(ORMModel):
    id: int
    name: str
    symbol: str
    alert_type: str
    condition_field: str
    comparison: str
    threshold: float
    priority: str
    message_template: str | None
    cooldown_seconds: int
    is_enabled: bool
    notify_discord: bool
    notify_email: bool
    last_fired_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AlertHistoryResponse(ORMModel):
    id: int
    rule_id: int
    rule_name: str
    symbol: str
    priority: str
    message: str
    field: str
    value: float | None
    threshold: float | None
    acknowledged: bool
    acknowledged_at: datetime | None
    triggered_at: datetime


class AcknowledgeResponse(BaseModel):
    status: Literal["acknowledged"] = "acknowledged"
    count: int = 1


# ═════════════════════════════════════════════════════════════════════
# Analytics
# ═════════════════════════════════════════════════════════════════════


class ReliabilityBin(BaseModel):
    n: int
    forecast: float  # mean forecast probability in the bin
    observed: float  # share of the bin's rows that were the class


class ReliabilityCurve(BaseModel):
    """Held-out forecasts of each class in 10 equal-width bins (empty bins omitted)."""

    down: list[ReliabilityBin]
    flat: list[ReliabilityBin]
    up: list[ReliabilityBin]


class FoldMetricsResponse(BaseModel):
    n_train: int
    n_test: int
    accuracy: float
    log_loss: float  # the calibrated fold model — the recipe that is served
    raw_log_loss: float  # its tree models before calibration
    brier: float
    brier_reliability: float
    brier_resolution: float
    brier_uncertainty: float
    prior_log_loss: float
    logistic_log_loss: float
    logistic_accuracy: float
    calibration: Literal["isotonic", "sigmoid", "none"]
    reliability: ReliabilityCurve
    # the class mix of labels already resolved at each prediction; None for older models
    trailing_prior_log_loss: float | None = None


class ModelMetrics(BaseModel):
    oos: dict[str, float]
    folds: list[FoldMetricsResponse]
    reliability: ReliabilityCurve | None = None  # pooled over the folds


class ModelInfoResponse(BaseModel):
    symbol: str
    status: Literal["warming_up", "training", "ready"]
    model_version: int
    model_id: int | None
    trained_at: str | None
    training_samples: int
    samples_available: int
    samples_required: int
    pending_labels: int
    horizon_s: int
    lookback_bars: int
    barrier_k: float
    calibration: str | None
    metrics: ModelMetrics
    class_prior: dict[str, float]
    feature_importance: dict[str, float]  # held-out log-loss increase when shuffled
    feature_importance_std: dict[str, float]
    feature_names: list[str]
    hyperparameters: dict[str, Any]
    next_retrain_in_samples: int
    training_runs: int
    drift: DriftSummary
    predictions_persisted: int
    predictions_resolved: int


class ModelRegistryEntry(BaseModel):
    id: int
    symbol: str
    name: str
    model_type: str
    version: int
    training_samples: int | None
    horizon_s: int | None
    metrics: dict[str, Any] | None
    feature_importance: dict[str, Any] | None
    hyperparameters: dict[str, Any] | None
    is_active: bool
    trained_at: str


class DriftOutcome(BaseModel):
    ts_ms: int
    p_up: float
    p_down: float
    predicted: int
    realised: int
    hit: bool
    log_loss: float
    realised_bps: float


class DriftResponse(BaseModel):
    symbol: str
    summary: DriftSummary
    series: list[DriftOutcome]


class ShapContribution(BaseModel):
    feature: str
    value: float
    shap: float


class ShapResponse(BaseModel):
    """SHAP of the served ensemble's tree models (raw log-odds, before calibration), averaged."""

    symbol: str
    predicted_class: Literal["up", "down", "flat"]
    probability: float  # the served, calibrated probability of the predicted class
    models_averaged: int
    base_value: float
    prediction_logit: float
    contributions: list[ShapContribution]


class SignalRuleResponse(BaseModel):
    id: str
    name: str
    priority: Literal["high", "medium", "low"]
    enter: dict[str, Any]
    exit: dict[str, Any]
    enter_text: str
    exit_text: str
    min_duration_s: float
    cooldown_s: float
    message: str
    action: str
    impact: str
    tags: list[str]
    enabled: bool
    active: bool


class SignalsStateResponse(BaseModel):
    symbol: str
    active: list[ActiveSignalPayload]
    recent: list[SignalTransitionPayload]


# ═════════════════════════════════════════════════════════════════════
# System
# ═════════════════════════════════════════════════════════════════════


__all_prediction__ = PredictionPayload  # re-exported for routers


class HealthResponse(BaseModel):
    """Summary health; always 200 — see `/health/live` and `/health/ready` for probes."""

    status: Literal["ok", "degraded"]
    version: str
    environment: str
    uptime_seconds: float
    data_source: str
    symbols: list[str]
    market_connected: bool
    ws_clients: int
    loop_lag_p99_ms: float | None = None
    timestamp: datetime


class LivenessResponse(BaseModel):
    """The process is up and its event loop answers (use for restart decisions)."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Ready to serve live data (use for traffic decisions); 503 when any check fails."""

    ready: bool
    checks: dict[str, bool]
    detail: dict[str, str]


class RootResponse(BaseModel):
    app: str
    version: str
    docs: str
    health: str
    api: str


# ═════════════════════════════════════════════════════════════════════
# Market & system read-outs
# ═════════════════════════════════════════════════════════════════════


class SymbolsResponse(BaseModel):
    active: list[str]
    default: str
    allowlist: list[str]
    source: str


class FeatureCatalogEntry(BaseModel):
    name: str
    label: str
    unit: str
    kind: Literal[
        "price", "bps", "ratio", "rate", "quantity", "zscore", "categorical", "probability"
    ]
    group: str
    description: str
    ops: list[str]
    values: list[str]


class SourceStats(BaseModel):
    """Every source reports these; each kind adds its own counters (hosts, steps, file…)."""

    model_config = ConfigDict(extra="allow")

    name: str
    status: str
    time_scale: float


class BookStats(BaseModel):
    state: str
    levels: int
    update_id: int
    resyncs: int
    updates_applied: int
    metric_scans: int
    pruned_levels: int


class MLRuntimeStats(BaseModel):
    status: Literal["warming_up", "training", "ready"]
    version: int
    samples: int
    training: bool
    last_training_s: float | None
    last_inference_ms: float | None
    inference_timeouts: int
    sessions: int
    prediction_backlog: int
    prediction_failed_flushes: int


class SymbolStats(BaseModel):
    symbol: str
    source: SourceStats
    status: str
    connected: bool
    book: BookStats
    events: int
    trades: int
    diffs: int
    dropped_diffs: int
    event_rate_per_s: float
    clock_skew_ms: float | None
    bars_closed: int
    bar_ring: int
    regime: RegimePayload
    ml: MLRuntimeStats | None
    intelligence_skipped_bars: int
    signals_active: int
    uptime_seconds: float


class WriterStats(BaseModel):
    written: int
    failed_flushes: int
    queued: int


class DiscordStats(BaseModel):
    enabled: bool
    sent: int
    failed: int


class AlertEngineStats(BaseModel):
    rules_cached: int
    evaluations: int
    fired: int
    discord: DiscordStats


class WSClientStats(BaseModel):
    symbol: str
    channels: list[str]
    sent: int
    dropped: int
    backlog: int
    connected_at_ms: int


class WSStats(BaseModel):
    clients: int
    total_sent: int
    per_client: list[WSClientStats]


class MarketStats(BaseModel):
    source: str
    symbols: dict[str, SymbolStats]
    writer: WriterStats
    alerts: AlertEngineStats
    backtests_running: list[int]
    ws: WSStats


class MarketStatsResponse(MarketStats):
    timestamp: str


class LoopLagStats(BaseModel):
    samples: int
    window_s: float
    current_ms: float | None = None
    p50_ms: float | None = None
    p99_ms: float | None = None
    max_ms: float | None = None


class SystemMetricsResponse(BaseModel):
    market: MarketStats
    ws: WSStats
    loop: LoopLagStats
    ml: dict[str, ModelInfoResponse]
    timestamp: str


# ═════════════════════════════════════════════════════════════════════
# Pages (keyset pagination, newest first)
# ═════════════════════════════════════════════════════════════════════
#
# A list endpoint returns `items` and `next_before`: pass it back as `before`
# for the next, older page; None means there is nothing older. Keyed by row
# id, so rows inserted meanwhile never shift or repeat a page.


class AlertHistoryPage(BaseModel):
    items: list[AlertHistoryResponse]
    next_before: int | None


class BacktestPage(BaseModel):
    items: list[BacktestResponse]
    next_before: int | None


class ModelRegistryPage(BaseModel):
    items: list[ModelRegistryEntry]
    next_before: int | None
