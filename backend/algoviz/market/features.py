"""
Streaming feature engine
========================

Event-driven, O(1) amortised per trade / book update. Holds the rolling
windows, the OFI windows, the volatility EWMA and the z-score baselines for
one symbol, and produces a `FeatureSnapshot` on demand (the 5 Hz broadcaster
and the 1 Hz bar close both read it; nothing is recomputed from scratch).

Book-derived metrics (microprice, liquidity bands, weighted imbalance) scan
the levels within 25 bps, so they are computed **lazily**: a diff only marks
the book dirty, and the scan runs when a snapshot is actually read.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from algoviz.config import Settings
from algoviz.market.baseline import BaselineSet
from algoviz.market.book import BookMetrics, LocalOrderBook
from algoviz.market.events import TradeEvent
from algoviz.market.ring import Ewm, TimeWindowSum, TradeWindow

_VOL_HORIZON_SCALE = math.sqrt(60.0)  # 1 s returns → 1-minute horizon


@dataclass(slots=True)
class FeatureSnapshot:
    symbol: str
    ts_ms: int
    source: str
    warmed_up: bool
    # price
    last_price: float | None
    mid: float | None
    microprice: float | None
    microprice_dev_bps: float | None
    vwap: float | None
    twap: float | None
    price_vs_vwap_bps: float | None
    session_change_pct: float | None
    # book
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
    # flow
    ofi_1s: float
    ofi_5s: float
    ofi_30s: float
    velocity: float
    velocity_baseline: float | None
    buy_pressure: float | None
    volume_30s: float
    trade_count_30s: int
    # vol
    volatility_bps: float | None
    # z
    spread_z: float | None
    velocity_z: float | None
    vol_z: float | None
    ofi_z: float | None
    imbalance_z: float | None
    liquidity_z: float | None
    # regime (filled by the service)
    regime: str | None
    regime_direction: float | None
    regime_source: str | None
    trend: str | None
    # model (filled by the service from the latest prediction)
    p_up: float | None = None
    p_down: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StreamingFeatureEngine:
    def __init__(self, symbol: str, cfg: Settings, source: str) -> None:
        self.symbol = symbol
        self.source = source
        self._cfg = cfg
        self._w30 = TradeWindow(cfg.VWAP_WINDOW)
        self._w_vel = TradeWindow(cfg.VELOCITY_WINDOW)
        self._ofi_1 = TimeWindowSum(1.0)
        self._ofi_5 = TimeWindowSum(5.0)
        self._ofi_30 = TimeWindowSum(30.0)
        self._vol = Ewm(cfg.VOLATILITY_WINDOW)  # on 1 s mid log-returns
        # std floors: (absolute, relative to |mean|). OFI and imbalance are centred
        # near zero, so only an absolute floor makes sense for them.
        self._baselines = BaselineSet(
            {
                "spread_bps": (1e-4, 0.05),
                "velocity": (0.2, 0.05),
                "volatility_bps": (0.05, 0.05),
                "ofi_5s": (0.02, 0.0),
                "imbalance_w": (0.02, 0.0),
                "liquidity_10bps": (0.1, 0.05),
            },
            cfg.EWMA_FAST_HALFLIFE_S,
            cfg.EWMA_SLOW_HALFLIFE_S,
            cfg.ZSCORE_WARMUP_S,
        )
        self._book_metrics: BookMetrics | None = None
        self._book: LocalOrderBook | None = None
        self._book_ts_ms = 0
        self._book_dirty = False
        self.book_scans = 0  # O(levels) metric computations (vs. updates, for the stats)
        self._last_trade: TradeEvent | None = None
        self._session_open: float | None = None
        self._prev_bar_mid: float | None = None
        self._last_ts_ms = 0
        self.regime: str | None = None
        self.regime_direction: float | None = None
        self.regime_source: str | None = None
        self.trend: str | None = None
        self.p_up: float | None = None
        self.p_down: float | None = None

    # ── Event handlers (O(1)) ─────────────────────────────────────

    def on_trade(self, ev: TradeEvent) -> None:
        self._last_trade = ev
        self._last_ts_ms = max(self._last_ts_ms, ev.ts_ms)
        if self._session_open is None:
            self._session_open = ev.price
        is_buy = not ev.is_buyer_maker
        self._w30.push(ev.ts_ms, ev.price, ev.qty, is_buy)
        self._w_vel.push(ev.ts_ms, ev.price, ev.qty, is_buy)

    def on_book(self, book: LocalOrderBook, ts_ms: int) -> None:
        """O(1): take the OFI accumulated by this update and mark the book metrics stale."""
        self._book = book
        self._book_ts_ms = ts_ms
        self._book_dirty = True
        self._last_ts_ms = max(self._last_ts_ms, ts_ms)
        e = book.take_ofi()
        if e != 0.0:
            self._ofi_1.push(ts_ms, e)
            self._ofi_5.push(ts_ms, e)
            self._ofi_30.push(ts_ms, e)

    def on_bar_close(self, ts_ms: int, mid: float | None) -> None:
        """1 Hz hook: volatility from bar-to-bar mid log-returns; baselines update."""
        if mid is not None and mid > 0:
            if self._prev_bar_mid:
                r = math.log(mid / self._prev_bar_mid)
                self._vol.update(ts_ms, r)
            self._prev_bar_mid = mid
        self.tick(ts_ms)
        snap = self.snapshot(ts_ms)
        self._baselines.update(
            ts_ms,
            {
                "spread_bps": snap.spread_bps,
                "velocity": snap.velocity,
                "volatility_bps": snap.volatility_bps,
                "ofi_5s": snap.ofi_5s,
                "imbalance_w": snap.imbalance_w,
                "liquidity_10bps": snap.liquidity_10bps,
            },
        )

    def tick(self, now_ms: int) -> None:
        """Decay windows without an event (quiet market)."""
        self._last_ts_ms = max(self._last_ts_ms, now_ms)
        self._w30.evict(now_ms)
        self._w_vel.evict(now_ms)
        self._ofi_1.evict(now_ms)
        self._ofi_5.evict(now_ms)
        self._ofi_30.evict(now_ms)

    # ── Snapshot ──────────────────────────────────────────────────

    @property
    def volatility_bps(self) -> float | None:
        if self._vol.n < 2:
            return None
        return self._vol.std * _VOL_HORIZON_SCALE * 10_000

    def _refresh_book(self) -> BookMetrics | None:
        if self._book_dirty and self._book is not None:
            self._book_dirty = False
            m = self._book.metrics(self._book_ts_ms)
            self.book_scans += 1
            if m is not None:
                self._book_metrics = m
        return self._book_metrics

    def snapshot(self, now_ms: int | None = None) -> FeatureSnapshot:
        ts = now_ms if now_ms is not None else self._last_ts_ms
        m = self._refresh_book()
        lt = self._last_trade
        last = lt.price if lt else None
        vwap, twap = self._w30.vwap, self._w30.twap
        velocity = self._w_vel.rate_per_s()
        vol = self.volatility_bps
        b = self._baselines
        vel_base = b.mean("velocity") if b.warmed_up(ts) else None

        return FeatureSnapshot(
            symbol=self.symbol,
            ts_ms=ts,
            source=self.source,
            warmed_up=b.warmed_up(ts),
            last_price=last,
            mid=m.mid if m else None,
            microprice=m.microprice if m else None,
            microprice_dev_bps=m.microprice_dev_bps if m else None,
            vwap=vwap,
            twap=twap,
            price_vs_vwap_bps=((last - vwap) / vwap * 10_000) if last and vwap else None,
            session_change_pct=(
                (last - self._session_open) / self._session_open * 100
                if last and self._session_open
                else None
            ),
            best_bid=m.best_bid if m else None,
            best_ask=m.best_ask if m else None,
            bid_qty=m.bid_qty if m else None,
            ask_qty=m.ask_qty if m else None,
            spread_bps=m.spread_bps if m else None,
            imbalance_l1=m.imbalance_l1 if m else None,
            imbalance_w=m.imbalance_w if m else None,
            liquidity_5bps=m.liquidity_5bps if m else None,
            liquidity_10bps=m.liquidity_10bps if m else None,
            liquidity_25bps=m.liquidity_25bps if m else None,
            book_slope_bid=m.slope_bid if m else None,
            book_slope_ask=m.slope_ask if m else None,
            ofi_1s=self._ofi_1.value,
            ofi_5s=self._ofi_5.value,
            ofi_30s=self._ofi_30.value,
            velocity=velocity,
            velocity_baseline=vel_base,
            buy_pressure=self._w30.buy_pressure,
            volume_30s=self._w30.volume,
            trade_count_30s=self._w30.count,
            volatility_bps=vol,
            spread_z=b.z("spread_bps", m.spread_bps if m else None, ts),
            velocity_z=b.z("velocity", velocity, ts),
            vol_z=b.z("volatility_bps", vol, ts),
            ofi_z=b.z("ofi_5s", self._ofi_5.value, ts),
            imbalance_z=b.z("imbalance_w", m.imbalance_w if m else None, ts),
            liquidity_z=b.z("liquidity_10bps", m.liquidity_10bps if m else None, ts),
            regime=self.regime,
            regime_direction=self.regime_direction,
            regime_source=self.regime_source,
            trend=self.trend,
            p_up=self.p_up,
            p_down=self.p_down,
        )

    @property
    def ofi_1s(self) -> float:
        return self._ofi_1.value

    @property
    def last_trade(self) -> TradeEvent | None:
        return self._last_trade

    @property
    def book_metrics(self) -> BookMetrics | None:
        return self._refresh_book()
