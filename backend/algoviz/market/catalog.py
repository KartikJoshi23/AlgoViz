"""
Feature catalog
===============

The one list of feature names the platform knows about. Used by:
- API validation of alert rules and strategy conditions;
- the frontend alert form and strategy builder (`GET /market/feature-catalog`);
- the ML feature pipeline and the persisted bar columns.

Adding a feature means adding it here **and** producing it in
`features.FeatureSnapshot`; a test asserts the two stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["price", "bps", "ratio", "rate", "quantity", "zscore", "categorical", "probability"]


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    label: str
    unit: str
    kind: Kind
    description: str
    group: str
    ops: tuple[str, ...] = ("gt", "gte", "lt", "lte", "eq")
    values: tuple[str, ...] = field(default=())  # categorical domain


_NUM = ("gt", "gte", "lt", "lte", "eq")
_CAT = ("eq", "in")

FEATURES: tuple[FeatureSpec, ...] = (
    # ── Price ────────────────────────────────────────────────────
    FeatureSpec(
        "last_price", "Last trade", "USDT", "price", "Price of the most recent trade", "price"
    ),
    FeatureSpec("mid", "Mid price", "USDT", "price", "(best bid + best ask) / 2", "price"),
    FeatureSpec(
        "microprice",
        "Microprice",
        "USDT",
        "price",
        "Queue-weighted mid: (Pb·Qa + Pa·Qb)/(Qa+Qb)",
        "price",
    ),
    FeatureSpec(
        "microprice_dev_bps",
        "Microprice deviation",
        "bps",
        "bps",
        "(microprice − mid)/mid; positive ⇒ pressure to tick up",
        "price",
    ),
    FeatureSpec(
        "vwap",
        "VWAP (30 s)",
        "USDT",
        "price",
        "Volume-weighted average trade price over the window",
        "price",
    ),
    FeatureSpec(
        "twap",
        "TWAP (30 s)",
        "USDT",
        "price",
        "Time/trade-weighted average price over the window",
        "price",
    ),
    FeatureSpec("price_vs_vwap_bps", "Price vs VWAP", "bps", "bps", "(last − vwap)/vwap", "price"),
    FeatureSpec(
        "session_change_pct",
        "Session change",
        "%",
        "ratio",
        "Change since the engine started",
        "price",
    ),
    # ── Book ─────────────────────────────────────────────────────
    FeatureSpec("spread_bps", "Spread", "bps", "bps", "(ask − bid)/mid", "book"),
    FeatureSpec(
        "imbalance_l1",
        "L1 imbalance",
        "ratio",
        "ratio",
        "(Qb − Qa)/(Qb + Qa) at the best level, −1…+1",
        "book",
    ),
    FeatureSpec(
        "imbalance_w",
        "Weighted imbalance",
        "ratio",
        "ratio",
        "Depth imbalance with exponential decay by distance from mid, −1…+1",
        "book",
    ),
    FeatureSpec(
        "liquidity_5bps",
        "Liquidity ±5 bps",
        "BTC",
        "quantity",
        "Resting quantity within 5 bps of mid (both sides)",
        "book",
    ),
    FeatureSpec(
        "liquidity_10bps",
        "Liquidity ±10 bps",
        "BTC",
        "quantity",
        "Resting quantity within 10 bps of mid (both sides)",
        "book",
    ),
    FeatureSpec(
        "liquidity_25bps",
        "Liquidity ±25 bps",
        "BTC",
        "quantity",
        "Resting quantity within 25 bps of mid (both sides)",
        "book",
    ),
    FeatureSpec(
        "book_slope_bid",
        "Bid slope",
        "BTC/bps",
        "quantity",
        "Cumulative bid depth per bps over the first 25 bps",
        "book",
    ),
    FeatureSpec(
        "book_slope_ask",
        "Ask slope",
        "BTC/bps",
        "quantity",
        "Cumulative ask depth per bps over the first 25 bps",
        "book",
    ),
    # ── Order flow ───────────────────────────────────────────────
    FeatureSpec(
        "ofi_1s",
        "OFI (1 s)",
        "BTC",
        "quantity",
        "Order-flow imbalance over 1 s; positive ⇒ net buying pressure",
        "flow",
    ),
    FeatureSpec("ofi_5s", "OFI (5 s)", "BTC", "quantity", "Order-flow imbalance over 5 s", "flow"),
    FeatureSpec(
        "ofi_30s", "OFI (30 s)", "BTC", "quantity", "Order-flow imbalance over 30 s", "flow"
    ),
    FeatureSpec(
        "velocity", "Trade velocity", "trades/s", "rate", "Trades per second over 3 s", "flow"
    ),
    FeatureSpec(
        "buy_pressure",
        "Buy pressure",
        "ratio",
        "ratio",
        "Aggressor-buy volume share over 30 s, 0…1",
        "flow",
    ),
    FeatureSpec(
        "volume_30s", "Volume (30 s)", "BTC", "quantity", "Traded quantity over 30 s", "flow"
    ),
    # ── Volatility ───────────────────────────────────────────────
    FeatureSpec(
        "volatility_bps",
        "Volatility",
        "bps",
        "bps",
        "EWMA std of 1 s mid log-returns, scaled to a 1-minute horizon",
        "vol",
    ),
    # ── z-scores ─────────────────────────────────────────────────
    FeatureSpec("spread_z", "Spread z", "σ", "zscore", "Spread vs its 15-min EWMA baseline", "z"),
    FeatureSpec("velocity_z", "Velocity z", "σ", "zscore", "Velocity vs baseline", "z"),
    FeatureSpec("vol_z", "Volatility z", "σ", "zscore", "Volatility vs baseline", "z"),
    FeatureSpec("ofi_z", "OFI z", "σ", "zscore", "OFI (5 s) vs baseline", "z"),
    FeatureSpec("imbalance_z", "Imbalance z", "σ", "zscore", "Weighted imbalance vs baseline", "z"),
    FeatureSpec("liquidity_z", "Liquidity z", "σ", "zscore", "Liquidity ±10 bps vs baseline", "z"),
    # ── Regime ───────────────────────────────────────────────────
    FeatureSpec(
        "regime",
        "Volatility state",
        "",
        "categorical",
        "HMM volatility state, labelled by the state's volatility z: calm < −0.25σ ≤ normal"
        " < 1σ ≤ elevated < 2.25σ ≤ extreme",
        "regime",
        ops=_CAT,
        values=("calm", "normal", "elevated", "extreme"),
    ),
    FeatureSpec(
        "trend",
        "Trend",
        "",
        "categorical",
        "Drift of the last 2 min of 1 s returns: up or down while its Newey–West t-statistic"
        " clears ±2 (released below 1.5), otherwise flat",
        "regime",
        ops=_CAT,
        values=("down", "flat", "up"),
    ),
    FeatureSpec(
        "regime_direction",
        "Trend strength",
        "",
        "ratio",
        "tanh(t / 2) of the drift t-statistic: −1 (down) … +1 (up)",
        "regime",
    ),
    # ── Model (Stage C) ──────────────────────────────────────────
    FeatureSpec(
        "p_up",
        "P(up)",
        "",
        "probability",
        "Calibrated probability of an up move within the horizon",
        "model",
    ),
    FeatureSpec(
        "p_down",
        "P(down)",
        "",
        "probability",
        "Calibrated probability of a down move within the horizon",
        "model",
    ),
)

FEATURE_REGISTRY: dict[str, FeatureSpec] = {f.name: f for f in FEATURES}
FEATURE_NAMES: tuple[str, ...] = tuple(FEATURE_REGISTRY)

# Names that exist only once the ML engine is active.
MODEL_FEATURES: frozenset[str] = frozenset({"p_up", "p_down"})


def is_valid_feature(name: str) -> bool:
    return name in FEATURE_REGISTRY


def validate_condition(field: str, op: str) -> str | None:
    """Return an error message or None when (field, op) is valid."""
    spec = FEATURE_REGISTRY.get(field)
    if spec is None:
        return f"unknown feature '{field}'"
    if op not in spec.ops:
        return f"operator '{op}' not valid for '{field}' (allowed: {', '.join(spec.ops)})"
    return None


def catalog_payload() -> list[dict[str, object]]:
    return [
        {
            "name": f.name,
            "label": f.label,
            "unit": f.unit,
            "kind": f.kind,
            "group": f.group,
            "description": f.description,
            "ops": list(f.ops),
            "values": list(f.values),
        }
        for f in FEATURES
    ]
