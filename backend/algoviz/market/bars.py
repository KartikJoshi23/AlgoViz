"""
1-second bars
=============

Bars close on **event time** (so replay at any speed yields identical bars)
with a wall-clock `flush()` safety net so a quiet market still produces empty
bars that carry the last mid forward. The service enriches each closed bar
with the feature snapshot at close; the enriched `Bar` is what gets
persisted, streamed, fed to the HMM and (Stage C) the ML pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from algoviz.market.events import TradeEvent

BAR_MS = 1000
# Bars are contiguous while the engine runs (the flush loop closes empty ones),
# so a jump larger than this between consecutive bars is an outage or restart.
SESSION_GAP_MS = 5_000

# Volatility states in ordinal order (calm → extreme) and trend directions
# (down → up). Streamed bars carry the index of each.
REGIME_LABELS: tuple[str, ...] = ("calm", "normal", "elevated", "extreme")
TREND_LABELS: tuple[str, ...] = ("down", "flat", "up")
_REGIME_CODE = {label: i for i, label in enumerate(REGIME_LABELS)}
_TREND_CODE = {label: i for i, label in enumerate(TREND_LABELS)}


@dataclass(slots=True)
class Bar:
    symbol: str
    ts_ms: int  # bar *open* time, aligned to the second
    source: str
    open: float
    high: float
    low: float
    close: float
    last_price: float | None
    volume: float
    buy_volume: float
    trade_count: int
    # enriched at close (None until the service fills them)
    spread_bps: float | None = None
    microprice: float | None = None
    imbalance: float | None = None
    imbalance_w: float | None = None
    ofi: float | None = None
    liquidity_5bps: float | None = None
    liquidity_10bps: float | None = None
    book_slope: float | None = None
    vwap: float | None = None
    velocity: float | None = None
    buy_pressure: float | None = None
    volatility_bps: float | None = None
    spread_z: float | None = None
    velocity_z: float | None = None
    vol_z: float | None = None
    ofi_z: float | None = None
    imbalance_z: float | None = None
    regime: str | None = None  # volatility state
    trend: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def vwap_bar(self) -> float | None:
        return self.extra.get("vwap_bar")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def compact(self) -> list[float | None]:
        """Column order shared with the WS `snapshot` / `bar` messages."""
        return [
            self.ts_ms, self.open, self.high, self.low, self.close, self.volume,
            self.buy_volume, self.trade_count, self.spread_bps, self.microprice,
            self.imbalance_w, self.ofi, self.velocity, self.volatility_bps,
            self.vwap, self.spread_z, self.ofi_z, self.vol_z,
            _REGIME_CODE.get(self.regime) if self.regime is not None else None,
            _TREND_CODE.get(self.trend) if self.trend is not None else None,
        ]  # fmt: skip


def trailing_segment(bars: list[Bar]) -> list[Bar]:
    """The bars after the last session gap (oldest → newest input)."""
    for i in range(len(bars) - 1, 0, -1):
        if bars[i].ts_ms - bars[i - 1].ts_ms > SESSION_GAP_MS:
            return bars[i:]
    return bars


BAR_COLUMNS: tuple[str, ...] = (
    "ts_ms", "open", "high", "low", "close", "volume", "buy_volume", "trade_count",
    "spread_bps", "microprice", "imbalance_w", "ofi", "velocity", "volatility_bps",
    "vwap", "spread_z", "ofi_z", "vol_z", "regime", "trend",
)  # fmt: skip


class BarBuilder:
    def __init__(
        self,
        symbol: str,
        source: str,
        on_close: Callable[[Bar], None],
    ) -> None:
        self.symbol = symbol
        self.source = source
        self._on_close = on_close
        self._bar_start: int | None = None
        self._o = self._h = self._l = self._c = 0.0
        self._last_price: float | None = None
        self._vol = 0.0
        self._buy_vol = 0.0
        self._n = 0
        self._pq = 0.0
        self._last_mid: float | None = None
        self.bars_closed = 0

    @staticmethod
    def _align(ts_ms: int) -> int:
        return ts_ms - (ts_ms % BAR_MS)

    def _open(self, start: int, mid: float | None) -> None:
        self._bar_start = start
        m = mid if mid is not None else (self._last_mid or self._last_price or 0.0)
        self._o = self._h = self._l = self._c = m
        self._vol = self._buy_vol = self._pq = 0.0
        self._n = 0

    def _close_current(self) -> None:
        assert self._bar_start is not None
        bar = Bar(
            symbol=self.symbol,
            ts_ms=self._bar_start,
            source=self.source,
            open=self._o,
            high=self._h,
            low=self._l,
            close=self._c,
            last_price=self._last_price,
            volume=self._vol,
            buy_volume=self._buy_vol,
            trade_count=self._n,
        )
        if self._vol > 0:
            bar.extra["vwap_bar"] = self._pq / self._vol
        self.bars_closed += 1
        self._on_close(bar)

    def _roll_to(self, ts_ms: int) -> None:
        """Close every bar whose window ended at or before `ts_ms`."""
        target = self._align(ts_ms)
        if self._bar_start is None:
            self._open(target, self._last_mid)
            return
        while self._bar_start + BAR_MS <= target:
            self._close_current()
            self._open(self._bar_start + BAR_MS, self._c)

    # ── Inputs ────────────────────────────────────────────────────

    def on_trade(self, ev: TradeEvent) -> None:
        self._roll_to(ev.ts_ms)
        self._last_price = ev.price
        self._vol += ev.qty
        self._pq += ev.price * ev.qty
        if not ev.is_buyer_maker:
            self._buy_vol += ev.qty
        self._n += 1
        if self._last_mid is None:  # no book yet — track trades as price
            self._update_px(ev.price)

    def on_mid(self, ts_ms: int, mid: float) -> None:
        self._roll_to(ts_ms)
        self._last_mid = mid
        self._update_px(mid)

    def _update_px(self, px: float) -> None:
        if self._o == 0.0:
            self._o = self._h = self._l = px
        self._c = px
        self._h = max(self._h, px)
        self._l = min(self._l, px)

    def flush(self, now_ms: int) -> None:
        """Wall-clock safety net: close bars that ended before `now_ms`."""
        if self._bar_start is None:
            if self._last_mid is not None or self._last_price is not None:
                self._open(self._align(now_ms), self._last_mid)
            return
        self._roll_to(now_ms)

    @property
    def current_start(self) -> int | None:
        return self._bar_start

    @property
    def last_mid(self) -> float | None:
        return self._last_mid
