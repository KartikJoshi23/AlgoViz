"""
ML feature vector
=================

Built from the trailing window of 1-second bars. Every feature is scale-free
— bps, ratios, z-scores, one-hots, and **quantities divided by their own
rolling median** (trade counts by the typical trades per second, volume and
order-flow imbalance by the typical volume per second, resting liquidity by
its typical depth, each over the last 30 minutes) — so the same model reads
BTC and a thinner symbol on one scale. Names are the contract the registry,
SHAP output and the frontend all use; `FEATURE_SCHEMA` hashes them together
with a version that is bumped whenever a definition changes.
"""

from __future__ import annotations

import hashlib
import math
from bisect import bisect_left, insort
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import islice

import numpy as np

from algoviz.market.bars import REGIME_LABELS, Bar

LOOKBACK = 60  # bars needed for a full vector
SCALE_WINDOW = 1_800  # bars behind each rolling median (30 min)
FEATURE_SCHEMA_VERSION = 2  # 2: quantities over rolling medians; volatility-state one-hots

FEATURE_NAMES: tuple[str, ...] = (
    # momentum (bps)
    "ret_1", "ret_5", "ret_10", "ret_30", "ret_60", "accel_5",
    # realised volatility
    "rv_10", "rv_60", "rv_ratio", "vol_bps", "vol_z",
    # spread
    "spread_bps", "spread_z", "spread_chg",
    # activity
    "velocity", "velocity_z", "trades_10", "volume_10", "buy_share_10",
    "buy_pressure", "buy_pressure_delta",
    # book
    "imbalance_l1", "imbalance_w", "imbalance_z", "imbalance_mom",
    "microprice_dev_bps", "liquidity_10bps", "liquidity_z", "liq_ratio_5_10", "book_slope",
    # order flow
    "ofi_1s", "ofi_5s", "ofi_30s", "ofi_z", "ofi_cum_10",
    # vwap
    "vwap_dev_bps",
    # distribution / pattern
    "skew_60", "kurt_60", "consec_up", "consec_down",
    # volatility-state one-hot
    "regime_calm", "regime_normal", "regime_elevated", "regime_extreme",
    # intraday seasonality
    "hour_sin", "hour_cos",
)  # fmt: skip

# Divided by the symbol's rolling medians (`QuantityScales`): counts, volume, depth, order flow.
SCALED_FEATURES: tuple[str, ...] = (
    "velocity", "trades_10", "volume_10", "liquidity_10bps", "book_slope",
    "ofi_1s", "ofi_5s", "ofi_30s", "ofi_cum_10",
)  # fmt: skip
N_FEATURES = len(FEATURE_NAMES)
FEATURE_SCHEMA = hashlib.sha256(
    f"{FEATURE_SCHEMA_VERSION}:{','.join(FEATURE_NAMES)}".encode()
).hexdigest()[:16]


class RollingMedian:
    """
    Median of the positive values among the last `window` pushes (zeros and
    gaps count towards the window but not the median): a sorted list beside a
    FIFO, so an update is a binary search plus one memmove.
    """

    def __init__(self, window: int = SCALE_WINDOW) -> None:
        self._window = window
        self._fifo: deque[float | None] = deque()
        self._sorted: list[float] = []

    def push(self, v: float | None) -> None:
        keep = v if v is not None and v > 0 and math.isfinite(v) else None
        self._fifo.append(keep)
        if keep is not None:
            insort(self._sorted, keep)
        if len(self._fifo) > self._window:
            old = self._fifo.popleft()
            if old is not None:
                del self._sorted[bisect_left(self._sorted, old)]

    @property
    def value(self) -> float | None:
        n = len(self._sorted)
        if n == 0:
            return None
        mid = n // 2
        return self._sorted[mid] if n % 2 else 0.5 * (self._sorted[mid - 1] + self._sorted[mid])

    def clear(self) -> None:
        self._fifo.clear()
        self._sorted.clear()


@dataclass(slots=True)
class QuantityScales:
    """A symbol's typical sizes: the rolling medians that make quantity features scale-free."""

    trades: RollingMedian = field(default_factory=RollingMedian)  # trades per 1 s bar
    volume: RollingMedian = field(default_factory=RollingMedian)  # base-asset volume per bar
    liquidity: RollingMedian = field(default_factory=RollingMedian)  # resting size within ±10 bps

    def push(self, bar: Bar) -> None:
        self.trades.push(float(bar.trade_count))
        self.volume.push(bar.volume)
        self.liquidity.push(bar.liquidity_10bps)

    def clear(self) -> None:
        self.trades.clear()
        self.volume.clear()
        self.liquidity.clear()

    def current(self) -> tuple[float, float, float]:
        """(trades, volume, liquidity) per bar; 1.0 until a positive value has been seen."""
        return (self.trades.value or 1.0, self.volume.value or 1.0, self.liquidity.value or 1.0)


def _f(v: float | None, default: float = 0.0) -> float:
    return default if v is None or not math.isfinite(v) else float(v)


def _ret_bps(closes: np.ndarray, n: int) -> float:
    if len(closes) <= n or closes[-1 - n] <= 0:
        return 0.0
    return float((closes[-1] / closes[-1 - n] - 1.0) * 10_000)


def _std_bps(rets: np.ndarray) -> float:
    return float(rets.std() * 10_000) if len(rets) > 1 else 0.0


def _consecutive(closes: np.ndarray) -> tuple[int, int]:
    ups = downs = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            if downs:
                break
            ups += 1
        elif closes[i] < closes[i - 1]:
            if ups:
                break
            downs += 1
        else:
            break
    return ups, downs


def feature_vector(bars: Iterable[Bar], scales: tuple[float, float, float]) -> np.ndarray | None:
    """
    Feature vector for the *last* bar in `bars`; None if fewer than LOOKBACK
    bars. `scales` is `QuantityScales.current()`: typical trades, volume and
    liquidity per bar, measured up to (and including) that bar only.
    """
    n = len(bars)  # type: ignore[arg-type]
    if n < LOOKBACK:
        return None
    # `bars` is usually a deque (no slicing); islice from the tail is O(LOOKBACK).
    w = list(islice(bars, n - LOOKBACK, None))
    last = w[-1]
    closes = np.asarray([b.close for b in w], dtype=np.float64)
    if closes[-1] <= 0 or np.any(closes <= 0):
        return None
    rets = np.diff(np.log(closes))
    rets_bps = rets * 10_000

    r5 = _ret_bps(closes, 5)
    r5_prev = float((closes[-6] / closes[-11] - 1.0) * 10_000) if closes[-11] > 0 else 0.0
    rv10, rv60 = _std_bps(rets[-10:]), _std_bps(rets)
    spreads = np.asarray([_f(b.spread_bps) for b in w])
    spread_chg = (
        float(spreads[-1] / spreads[-10:].mean() - 1.0) if spreads[-10:].mean() > 0 else 0.0
    )
    trades10 = float(sum(b.trade_count for b in w[-10:]))
    vol10 = float(sum(b.volume for b in w[-10:]))
    buy10 = float(sum(b.buy_volume for b in w[-10:]))
    imb_w = [_f(b.imbalance_w) for b in w]
    bp = [_f(b.buy_pressure, 0.5) for b in w]
    ofi = [_f(b.ofi) for b in w]
    liq5, liq10 = _f(last.liquidity_5bps), _f(last.liquidity_10bps)
    vwap = _f(last.vwap)
    vwap_dev = (last.close - vwap) / vwap * 10_000 if vwap > 0 else 0.0
    skew = (
        float(((rets_bps - rets_bps.mean()) ** 3).mean() / (rets_bps.std() ** 3))
        if rets_bps.std() > 0
        else 0.0
    )
    kurt = (
        float(((rets_bps - rets_bps.mean()) ** 4).mean() / (rets_bps.std() ** 4) - 3.0)
        if rets_bps.std() > 0
        else 0.0
    )
    ups, downs = _consecutive(closes[-20:])
    per_trades, per_volume, per_liq = scales
    regime = last.regime or ""
    hour = datetime.fromtimestamp(last.ts_ms / 1000, tz=UTC)
    frac = (hour.hour * 3600 + hour.minute * 60 + hour.second) / 86_400.0
    extra = last.extra or {}

    vec = np.array(
        [
            _ret_bps(closes, 1), r5, _ret_bps(closes, 10), _ret_bps(closes, 30), _ret_bps(closes, 60),
            r5 - r5_prev,
            rv10, rv60, (rv10 / rv60) if rv60 > 0 else 1.0, _f(last.volatility_bps), _f(last.vol_z),
            spreads[-1], _f(last.spread_z), spread_chg,
            _f(last.velocity) / per_trades, _f(last.velocity_z), trades10 / (10 * per_trades),
            vol10 / (10 * per_volume), (buy10 / vol10) if vol10 > 0 else 0.5,
            bp[-1], bp[-1] - bp[-10],
            _f(last.imbalance), imb_w[-1], _f(last.imbalance_z), imb_w[-1] - imb_w[-10],
            _f(extra.get("microprice_dev_bps")), liq10 / per_liq, _f(extra.get("liquidity_z")),
            (liq5 / liq10) if liq10 > 0 else 0.0, _f(last.book_slope) * 10 / per_liq,
            ofi[-1] / per_volume, _f(extra.get("ofi_5s")) / (5 * per_volume),
            _f(extra.get("ofi_30s")) / (30 * per_volume), _f(last.ofi_z),
            float(sum(ofi[-10:])) / (10 * per_volume),
            vwap_dev,
            skew, kurt, float(ups), float(downs),
            *[1.0 if regime == lab else 0.0 for lab in REGIME_LABELS],
            math.sin(2 * math.pi * frac), math.cos(2 * math.pi * frac),
        ],
        dtype=np.float64,
    )  # fmt: skip
    assert vec.shape == (N_FEATURES,), vec.shape
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
