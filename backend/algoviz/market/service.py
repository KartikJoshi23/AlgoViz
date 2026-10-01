"""
Market service
==============

One `SymbolEngine` per symbol wires a data source into the book, the
streaming feature engine, the bar builder, the regime detector, the hub and
the bar writer, following the cadence tiers in implementation-plan §2.12:

    per event  → book apply + OFI, O(1) feature updates, bar accumulation
    10 Hz      → trades batches;  5 Hz → features + book (subscribers only)
    1 Hz       → bar close: z-scores, regime decode, ML bookkeeping, bar
                 broadcast + persistence; then, off the close path, the
                 intelligence tier (prediction on the inference thread →
                 signals → alerts): latest bar wins on a real-time feed (it
                 never queues); lossless with backpressure on an unpaced one
    periodic   → HMM refit (worker process), wall-clock bar flush safety net,
                 feed staleness watchdog

Nothing CPU-heavy runs on the event loop: the loop owns the feed, and a feed
that misses its keepalive is a feed that disconnects.

`MarketService` owns the engines, the writer, and the hub wiring.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from algoviz.alerts.evaluator import AlertEvaluator
from algoviz.alerts.notify import DiscordNotifier
from algoviz.backtest.service import BacktestRunner
from algoviz.config import Settings, settings
from algoviz.core.metrics import FEED_LATENCY
from algoviz.core.time import utcnow
from algoviz.core.workers import Offload, run_isolated
from algoviz.db import async_session
from algoviz.market.bars import BAR_COLUMNS, Bar, BarBuilder, trailing_segment
from algoviz.market.book import LocalOrderBook
from algoviz.market.events import (
    DepthDiffEvent,
    DepthSnapshotEvent,
    MarketEvent,
    SourceStatusEvent,
    TradeEvent,
)
from algoviz.market.features import FeatureSnapshot, StreamingFeatureEngine
from algoviz.market.persistence import BarWriter, load_bars
from algoviz.market.regime import RegimeDetector, RegimeState, fit_regime
from algoviz.market.sources import MarketSource, create_source
from algoviz.ml.engine import InferenceJob, MLEngine
from algoviz.signals.engine import SignalEngine
from algoviz.ws.hub import Hub, ws_manager

logger = logging.getLogger("algoviz.market")

BROADCAST_TICK_S = 0.1  # 10 Hz base tick
FEATURES_EVERY_TICKS = 2  # 5 Hz
BOOK_EVERY_TICKS = 2  # 5 Hz
BOOK_DEPTH = 50
BAR_RING = 600
TRADE_RING = 200
SNAPSHOT_DEBOUNCE_S = 2.0
INTEL_BACKLOG = 4  # unpaced sources pause once this many closed bars await the intelligence tier


@dataclass(slots=True)
class _IntelJob:
    """One closed bar's work for the intelligence tier (built at bar close)."""

    ctx: dict[str, Any]
    ts_close: int
    inference: InferenceJob | None


class SymbolEngine:
    def __init__(
        self,
        symbol: str,
        cfg: Settings,
        source: MarketSource,
        hub: Hub,
        writer: BarWriter | None,
        *,
        preload: bool = True,
        intelligence: bool = True,
        alerts: AlertEvaluator | None = None,
        offload: Offload | None = None,
    ) -> None:
        self.symbol = symbol.upper()
        self._preload = preload
        self.cfg = cfg
        self.source = source
        self.hub = hub
        self.writer = writer
        # Where model training and HMM fits run: a spawned process by default.
        self._offload: Offload = offload or partial(
            run_isolated, timeout_s=cfg.REGIME_FIT_TIMEOUT_S, threads=cfg.ML_TRAIN_THREADS or None
        )
        self.ml: MLEngine | None = (
            MLEngine(
                self.symbol,
                cfg,
                async_session,
                persist=writer is not None,
                offload=offload,  # None → MLEngine's own process offload with the training timeout
            )
            if intelligence
            else None
        )
        self.signals = SignalEngine() if intelligence else None
        self.alerts = alerts
        self.book = LocalOrderBook(self.symbol)
        self.features = StreamingFeatureEngine(self.symbol, cfg, source.name)
        self.bars = BarBuilder(self.symbol, source.name, self._on_bar_close)
        self.regime = RegimeDetector()
        self.bar_ring: deque[Bar] = deque(maxlen=BAR_RING)
        self.trade_ring: deque[TradeEvent] = deque(maxlen=TRADE_RING)
        self._unsent_trades: list[TradeEvent] = []
        self._status = SourceStatusEvent(self.symbol, 0, "idle")
        self._last_regime: RegimeState | None = None
        self._prediction: dict[str, Any] | None = None
        self._profile_band: float | None = None  # EWMA of the adaptive depth-profile band
        self._last_snapshot_req = 0.0
        self._regime_fit_task: asyncio.Task[None] | None = None
        self._tasks: list[asyncio.Task[None]] = []
        # Intelligence tier. Real-time feed: latest bar wins (a busy tier skips bars,
        # never queues them). Unpaced source: every bar, and the source waits for room.
        self._intel_queue: deque[_IntelJob] = deque()
        self._intel_wake = asyncio.Event()
        self._intel_room = asyncio.Event()
        self._intel_room.set()
        self._lossless = source.unpaced
        if self._lossless and intelligence:
            source.backpressure = self._wait_for_intel_room
        # Feed watchdog (monotonic clock of the last market event).
        self._last_event_mono = time.monotonic()
        self._stale = False
        self.started_at = utcnow()
        # counters
        self.n_events = self.n_trades = self.n_diffs = self.n_dropped_diffs = 0
        self.n_intel_skipped = self.n_pruned_levels = 0
        self._ev_window: deque[float] = deque(maxlen=2000)  # event arrival times (rate metric)
        self._loop: asyncio.AbstractEventLoop | None = None
        # Estimated (local wall clock − exchange event time), EWMA-smoothed. Exchange
        # clocks and local clocks routinely differ by seconds; windows and bar
        # boundaries must live entirely in event time.
        self._skew_ms: float | None = None
        self._latency = FEED_LATENCY.labels(self.symbol)
        self._last_event_ms = 0

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        history: list[Bar] = []
        if self._preload:
            history = await self._preload_bars()
        if self.ml is not None:
            await self.ml.start(history)
        self._tasks = [
            asyncio.create_task(self._run_source(), name=f"src-{self.symbol}"),
            asyncio.create_task(self._broadcast_loop(), name=f"bcast-{self.symbol}"),
            asyncio.create_task(self._bar_flush_loop(), name=f"bars-{self.symbol}"),
        ]
        if self.ml is not None:
            self._tasks.append(
                asyncio.create_task(self._intelligence_loop(), name=f"intel-{self.symbol}")
            )
        logger.info("engine started (%s, source=%s)", self.symbol, self.source.name)

    async def stop(self) -> None:
        pending = [*self._tasks]
        if self._regime_fit_task is not None:
            pending.append(self._regime_fit_task)
        for t in pending:
            t.cancel()
        for t in pending:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks.clear()
        if self.ml is not None:
            await self.ml.stop()

    async def _preload_bars(self) -> list[Bar]:
        """
        Hand the full history to the ML engine (its training set is rebuilt,
        not reset; it splits the history at session gaps itself) and, when the
        newest session ended moments ago, resume the charts and the regime
        detector from it. Older history is never spliced onto the live stream.
        """
        try:
            bars = await load_bars(
                async_session,
                self.symbol,
                source=self.source.name,
                limit=self.cfg.ML_HISTORY_BARS,
                newest_first=True,
            )
        except Exception:
            logger.exception("bar preload failed")
            return []
        bars.reverse()  # oldest → newest
        if not bars:
            return []
        last = trailing_segment(bars)[-BAR_RING:]
        gap_s = (self.now_ms() - last[-1].ts_ms) / 1000
        resumed = gap_s <= self.cfg.BAR_RESUME_MAX_GAP_S
        if resumed:
            for b in last:
                self.bar_ring.append(b)
                self.regime.push_bar(b)
        logger.info(
            "%s: %d bars of history for the model; %s",
            self.symbol,
            len(bars),
            f"charts resumed from the last {len(last)} bars"
            if resumed
            else f"newest bar is {gap_s / 60:.0f} min old, charts start fresh",
        )
        return bars

    async def _run_source(self) -> None:
        try:
            await self.source.run(self.handle_event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s source crashed", self.symbol)
            self._status = SourceStatusEvent(self.symbol, self.source.now_ms(), "failed")

    # ── Clock ─────────────────────────────────────────────────────

    def now_ms(self) -> int:
        """Current time in the *event* clock domain."""
        src_now = self.source.now_ms()
        if self.source.wall_clock and self._skew_ms is not None:
            return int(src_now - self._skew_ms)
        return src_now

    def _observe_skew(self, ev_ts_ms: int) -> None:
        if not self.source.wall_clock:
            return
        skew = self.source.now_ms() - ev_ts_ms
        self._latency.observe(skew)
        self._skew_ms = (
            skew if self._skew_ms is None else self._skew_ms + 0.05 * (skew - self._skew_ms)
        )

    # ── Per-event tier ────────────────────────────────────────────

    def handle_event(self, ev: MarketEvent) -> None:
        """Entry point for sources. Never raises: a bug here must not tear down the feed."""
        try:
            self._handle_event(ev)
        except Exception:
            logger.exception("%s event handling failed (%s)", self.symbol, type(ev).__name__)

    def _handle_event(self, ev: MarketEvent) -> None:
        self.n_events += 1
        self._ev_window.append(time.monotonic())
        if isinstance(ev, TradeEvent | DepthDiffEvent):
            self._observe_skew(ev.ts_ms)
            self._last_event_ms = max(self._last_event_ms, ev.ts_ms)
            self._last_event_mono = time.monotonic()
        if isinstance(ev, TradeEvent):
            self.n_trades += 1
            self.features.on_trade(ev)
            self.bars.on_trade(ev)
            self.trade_ring.append(ev)
            self._unsent_trades.append(ev)
        elif isinstance(ev, DepthDiffEvent):
            self.n_diffs += 1
            if self.book.apply_diff(ev):
                self._after_book_update(ev.ts_ms)
            else:
                self.n_dropped_diffs += 1
                self._maybe_request_snapshot()
        elif isinstance(ev, DepthSnapshotEvent):
            self.book.apply_snapshot(ev)
            if self.book.synced:
                # A REST snapshot is stamped with the local clock; keep bars and windows
                # in exchange time by using the latest event time seen instead.
                self._after_book_update(self._last_event_ms or self.now_ms())
                logger.info(
                    "%s book synced (%d levels, id=%d, resyncs=%d)",
                    self.symbol,
                    len(self.book),
                    self.book.last_update_id,
                    self.book.resyncs,
                )
            else:
                # A buffered diff gapped right after the snapshot: fetch another.
                self._maybe_request_snapshot(force=True)
        elif isinstance(ev, SourceStatusEvent):
            self._status = ev
            self.hub.publish("status", self.symbol, self._status_payload())
            if ev.status == "connected":
                self.book.mark_syncing()
                self._maybe_request_snapshot(force=True)

    def _after_book_update(self, ts_ms: int) -> None:
        self.features.on_book(self.book, ts_ms)
        mid = self.book.mid
        if mid is not None:
            self.bars.on_mid(ts_ms, mid)

    def _maybe_request_snapshot(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_snapshot_req < SNAPSHOT_DEBOUNCE_S:
            return
        self._last_snapshot_req = now
        self.book.mark_syncing()
        if self._loop is not None:
            self._loop.create_task(self.source.request_snapshot())

    # ── 10 Hz / 5 Hz tier ─────────────────────────────────────────

    async def _broadcast_loop(self) -> None:
        tick = 0
        while True:
            try:
                if self._unsent_trades:
                    batch, self._unsent_trades = self._unsent_trades[-100:], []
                    self.hub.publish("trades", self.symbol, [self.trade_payload(t) for t in batch])
                if tick % FEATURES_EVERY_TICKS == 0 and self.hub.has_subscribers(
                    "features", self.symbol
                ):
                    self.hub.publish(
                        "features", self.symbol, self.features.snapshot(self.now_ms()).to_dict()
                    )
                if tick % BOOK_EVERY_TICKS == 0 and self.hub.has_subscribers("book", self.symbol):
                    payload = self.book_payload()
                    if payload is not None:
                        self.hub.publish("book", self.symbol, payload)
                tick += 1
            except Exception:
                logger.exception("%s broadcast loop error", self.symbol)
            await asyncio.sleep(BROADCAST_TICK_S)

    async def _bar_flush_loop(self) -> None:
        """Wall-clock safety net: close bars even when no events arrive; watch the feed."""
        while True:
            await asyncio.sleep(1.0)
            try:
                now = self.now_ms()
                self.features.tick(now)
                self.bars.flush(now)
                self._check_feed(time.monotonic())
            except Exception:
                logger.exception("%s bar flush error", self.symbol)

    def _check_feed(self, now_mono: float) -> None:
        """A connected source that has gone quiet is reported as `stale` until data resumes."""
        idle = now_mono - self._last_event_mono
        stale = self._status.status == "connected" and idle > self.cfg.FEED_STALE_S
        if stale != self._stale:
            self._stale = stale
            if stale:
                logger.warning("%s feed stale: no market data for %.0fs", self.symbol, idle)
            self.hub.publish("status", self.symbol, self._status_payload())

    # ── 1 Hz tier (bar close) ─────────────────────────────────────

    def _on_bar_close(self, bar: Bar) -> None:
        ts_close = bar.ts_ms + 1000
        self.features.on_bar_close(ts_close, bar.close if bar.close > 0 else None)
        snap = self.features.snapshot(ts_close)
        self._enrich(bar, snap)

        state = self.regime.push_bar(bar)
        bar.regime = state.label
        bar.trend = state.trend
        self.features.regime = state.label
        self.features.regime_direction = state.direction
        self.features.regime_source = state.source
        self.features.trend = state.trend
        if (
            self._last_regime is None
            or state.label != self._last_regime.label
            or state.trend != self._last_regime.trend
            or state.source != self._last_regime.source
        ):
            self.hub.publish("regime", self.symbol, self._regime_payload(state))
        self._last_regime = state

        self.bar_ring.append(bar)
        if self.writer is not None:
            self.writer.enqueue(bar)
        self.hub.publish(
            "bars", self.symbol, {"columns": list(BAR_COLUMNS), "rows": [bar.compact()]}
        )
        if self.book.synced:
            self.n_pruned_levels += self.book.prune(self.cfg.BOOK_PRUNE_BPS)

        if self.ml is not None:
            try:
                inference = self.ml.ingest_bar(bar)  # bookkeeping only; predicting happens below
            except Exception:
                logger.exception("%s ML bookkeeping error", self.symbol)
                inference = None
            ctx = snap.to_dict()
            ctx["regime"] = state.label
            ctx["regime_direction"] = state.direction
            ctx["trend"] = state.trend
            self._submit_intel(_IntelJob(ctx, ts_close, inference))
        self._maybe_refit_regime()

    # ── Intelligence tier (off the bar-close path) ────────────────

    def _submit_intel(self, job: _IntelJob) -> None:
        if not self._lossless and self._intel_queue:
            self.n_intel_skipped += len(
                self._intel_queue
            )  # still busy with older bars: newest wins
            self._intel_queue.clear()
        self._intel_queue.append(job)
        if len(self._intel_queue) >= INTEL_BACKLOG:
            self._intel_room.clear()
        self._intel_wake.set()

    async def _wait_for_intel_room(self) -> None:
        await asyncio.sleep(0)  # always yield, even when there is room
        await self._intel_room.wait()

    async def _intelligence_loop(self) -> None:
        while True:
            await self._intel_wake.wait()
            self._intel_wake.clear()
            while self._intel_queue:
                job = self._intel_queue.popleft()
                if len(self._intel_queue) < INTEL_BACKLOG:
                    self._intel_room.set()
                try:
                    await self._intelligence_tier(job)
                except Exception:
                    logger.exception("%s intelligence tier error", self.symbol)

    async def _intelligence_tier(self, job: _IntelJob) -> None:
        """ML prediction (inference thread) → signal rules → user alert rules, for one closed bar."""
        assert self.ml is not None and self.signals is not None
        if job.inference is not None:
            pred = await self.ml.predict(job.inference)
            if pred is not None:
                self._prediction = pred
                self.features.p_up = pred.get("p_up")
                self.features.p_down = pred.get("p_down")
                self.hub.publish("prediction", self.symbol, pred)

        ctx = job.ctx
        ctx["p_up"] = self.features.p_up
        ctx["p_down"] = self.features.p_down
        try:
            transitions = self.signals.evaluate(ctx, job.ts_close)
            if transitions:
                self.hub.publish(
                    "signals",
                    self.symbol,
                    {
                        "symbol": self.symbol,
                        "transitions": [t.payload() for t in transitions],
                        "active": self.signals.active(job.ts_close),
                    },
                )
        except Exception:
            logger.exception("%s signal tier error", self.symbol)

        if self.alerts is not None:
            try:
                await self.alerts.evaluate(self.symbol, ctx, job.ts_close)
            except Exception:
                logger.exception("%s alert evaluation failed", self.symbol)

    @staticmethod
    def _enrich(bar: Bar, s: FeatureSnapshot) -> None:
        bar.spread_bps = s.spread_bps
        bar.microprice = s.microprice
        bar.imbalance = s.imbalance_l1
        bar.imbalance_w = s.imbalance_w
        bar.ofi = s.ofi_1s
        bar.liquidity_5bps = s.liquidity_5bps
        bar.liquidity_10bps = s.liquidity_10bps
        if s.book_slope_bid is not None and s.book_slope_ask is not None:
            bar.book_slope = (s.book_slope_bid + s.book_slope_ask) / 2
        bar.vwap = s.vwap
        bar.velocity = s.velocity
        bar.buy_pressure = s.buy_pressure
        bar.volatility_bps = s.volatility_bps
        bar.spread_z = s.spread_z
        bar.velocity_z = s.velocity_z
        bar.vol_z = s.vol_z
        bar.ofi_z = s.ofi_z
        bar.imbalance_z = s.imbalance_z
        bar.extra.update(
            {
                "ofi_5s": s.ofi_5s,
                "ofi_30s": s.ofi_30s,
                "microprice_dev_bps": s.microprice_dev_bps,
                "liquidity_z": s.liquidity_z,
            }
        )

    def _maybe_refit_regime(self) -> None:
        if self._loop is None or not self.regime.needs_refit():
            return
        if self._regime_fit_task is not None and not self._regime_fit_task.done():
            return
        X = self.regime.training_matrix()
        version = self.regime.model_version + 1
        self.regime.mark_refit_started()
        self._regime_fit_task = self._loop.create_task(
            self._refit_regime(X, version), name=f"regime-fit-{self.symbol}"
        )

    async def _refit_regime(self, X: Any, version: int) -> None:
        try:
            self.regime.install(await self._offload(fit_regime, X, version))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s regime refit failed", self.symbol)
        finally:
            self.regime.refit_finished()

    # ── Payloads ──────────────────────────────────────────────────

    @staticmethod
    def trade_payload(t: TradeEvent) -> dict[str, Any]:
        return {
            "ts_ms": t.ts_ms,
            "price": t.price,
            "qty": t.qty,
            "side": t.side,
            "trade_id": t.trade_id,
        }

    def book_payload(self, depth: int = BOOK_DEPTH) -> dict[str, Any] | None:
        m = self.features.book_metrics  # the lazily refreshed scan, shared with the features
        if m is None or not self.book.synced:
            return None
        bids, asks = self.book.top(depth)
        band = self._adaptive_band()
        pb, pa = self.book.depth_profile(settings.BOOK_PROFILE_BINS, band)
        return {
            "symbol": self.symbol,
            "ts_ms": self.book.last_ts_ms,
            "bids": [[p, q] for p, q in bids],
            "asks": [[p, q] for p, q in asks],
            "profile": {
                "band_bps": round(band, 3),
                "bins": settings.BOOK_PROFILE_BINS,
                "bids": [round(x, 4) for x in pb],
                "asks": [round(x, 4) for x in pa],
            },
            "mid": m.mid,
            "microprice": m.microprice,
            "spread_bps": m.spread_bps,
            "imbalance_l1": m.imbalance_l1,
            "imbalance_w": m.imbalance_w,
            "ofi_1s": self.features.ofi_1s,
            "liquidity_10bps": m.liquidity_10bps,
            "levels": m.levels,
            "update_id": self.book.last_update_id,
        }

    def _adaptive_band(self) -> float:
        """Half-band for the depth profile: where most of the in-band depth sits, smoothed."""
        reach = self.book.depth_reach(settings.BOOK_PROFILE_REACH, settings.BOOK_PROFILE_BPS)
        target = min(settings.BOOK_PROFILE_BPS, max(settings.BOOK_PROFILE_MIN_BPS, reach * 1.15))
        if self._profile_band is None:
            self._profile_band = target
        else:
            self._profile_band += 0.05 * (target - self._profile_band)  # ~4 s at 5 Hz
        return self._profile_band

    def _regime_payload(self, state: RegimeState | None = None) -> dict[str, Any]:
        s = state or self.regime.current()
        return {
            "symbol": self.symbol,
            "label": s.label,
            "direction": s.direction,
            "trend": s.trend,
            "trend_t": s.trend_t,
            "probs": s.probs,
            "source": s.source,
            "model_version": s.model_version,
            "bars_seen": s.bars_seen,
        }

    def _status_payload(self) -> dict[str, Any]:
        if self._stale:
            idle = time.monotonic() - self._last_event_mono
            status, detail = "stale", f"no market data for {idle:.0f}s"
        else:
            status, detail = self._status.status, self._status.detail
        return {
            "symbol": self.symbol,
            "status": status,
            "detail": detail,
            "source": self.source.name,
        }

    def client_snapshot(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "features": self.features.snapshot(self.now_ms()).to_dict(),
            "book": self.book_payload(),
            "bars": {"columns": list(BAR_COLUMNS), "rows": [b.compact() for b in self.bar_ring]},
            "trades": [self.trade_payload(t) for t in list(self.trade_ring)[-50:]],
            "regime": self._regime_payload(),
            "signals": self.signals.active(self.now_ms()) if self.signals else [],
            "prediction": self._prediction,
            "source_status": self._status_payload(),
        }

    # ── Stats ─────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self.source.connected

    def event_rate(self) -> float:
        if len(self._ev_window) < 2:
            return 0.0
        span = self._ev_window[-1] - self._ev_window[0]
        return len(self._ev_window) / span if span > 0 else 0.0

    def stats(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "source": self.source.stats(),
            "status": (
                "stale"
                if self._stale
                else self._status.status
                if self._status.status != "idle"
                else self.source.status
            ),
            "connected": self.connected,
            "book": {
                "state": self.book.state,
                "levels": len(self.book),
                "update_id": self.book.last_update_id,
                "resyncs": self.book.resyncs,
                "updates_applied": self.book.updates_applied,
                "metric_scans": self.features.book_scans,
                "pruned_levels": self.n_pruned_levels,
            },
            "events": self.n_events,
            "trades": self.n_trades,
            "diffs": self.n_diffs,
            "dropped_diffs": self.n_dropped_diffs,
            "event_rate_per_s": round(self.event_rate(), 1),
            "clock_skew_ms": round(self._skew_ms) if self._skew_ms is not None else None,
            "bars_closed": self.bars.bars_closed,
            "bar_ring": len(self.bar_ring),
            "regime": self._regime_payload(),
            "ml": (
                {
                    "status": "ready"
                    if self.ml.ready
                    else ("training" if self.ml.training else "warming_up"),
                    "version": self.ml.version,
                    "samples": self.ml.samples,
                    **self.ml.runtime_stats(),
                }
                if self.ml
                else None
            ),
            "intelligence_skipped_bars": self.n_intel_skipped,
            "signals_active": len(self.signals.active(self.now_ms())) if self.signals else 0,
            "uptime_seconds": (utcnow() - self.started_at).total_seconds(),
        }


class MarketService:
    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or settings
        self.engines: dict[str, SymbolEngine] = {}
        self.writer: BarWriter | None = None
        self._running = False
        self._source_factory: Callable[[Settings, str], MarketSource] = create_source
        self.notifier = DiscordNotifier(self.cfg.DISCORD_WEBHOOK_URL)
        self.alert_evaluator = AlertEvaluator(async_session, ws_manager, self.notifier)
        self.backtests = BacktestRunner(self.cfg, async_session, ws_manager)
        # Configure the hub up front so hello/snapshot work even if the engine is off.
        ws_manager.configure(
            symbols=self.cfg.SYMBOLS,
            snapshot_provider=self.client_snapshot,
            hello_provider=self.hello,
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.writer = BarWriter(
            async_session,
            retention_days=self.cfg.SNAPSHOT_RETENTION_DAYS,
            prediction_retention_days=self.cfg.PREDICTION_RETENTION_DAYS,
            alert_retention_days=self.cfg.ALERT_HISTORY_RETENTION_DAYS,
        )
        await self.writer.start()
        await self.alert_evaluator.refresh()
        for sym in self.cfg.SYMBOLS:
            source = self._source_factory(self.cfg, sym)
            engine = SymbolEngine(
                sym, self.cfg, source, ws_manager, self.writer, alerts=self.alert_evaluator
            )
            self.engines[sym] = engine
            await engine.start()
        logger.info(
            "market service started: %s (source=%s)", ", ".join(self.engines), self.cfg.DATA_SOURCE
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        # Order: backtests (they write results), then the feeds and their ML engines
        # (prediction flush), then the bar writer's final flush, then notifications.
        await self.backtests.stop()
        for engine in self.engines.values():
            await engine.stop()
        self.engines.clear()
        if self.writer:
            await self.writer.stop()
        await self.notifier.aclose()
        logger.info("market service stopped")

    # ── Accessors ─────────────────────────────────────────────────

    def get(self, symbol: str | None = None) -> SymbolEngine | None:
        if not self.engines:
            return None
        if symbol is None:
            return self.engines.get(self.cfg.default_symbol) or next(iter(self.engines.values()))
        return self.engines.get(symbol.upper())

    @property
    def is_connected(self) -> bool:
        return any(e.connected for e in self.engines.values())

    async def client_snapshot(self, symbol: str) -> dict[str, Any] | None:
        engine = self.get(symbol)
        return engine.client_snapshot() if engine else None

    def hello(self, subscribed: list[str]) -> dict[str, Any]:
        from algoviz import __version__
        from algoviz.schemas.ws import CHANNELS

        first = self.get()
        return {
            "version": __version__,
            "symbols": self.cfg.SYMBOLS,
            "default_symbol": self.cfg.default_symbol,
            "source": self.cfg.DATA_SOURCE,
            "time_scale": first.source.time_scale if first else 1.0,  # 0 = unpaced
            "channels": list(CHANNELS),
            "subscribed": subscribed,
            "bar_columns": list(BAR_COLUMNS),
            "server_time_ms": int(utcnow().timestamp() * 1000),
        }

    def stats(self) -> dict[str, Any]:
        return {
            "source": self.cfg.DATA_SOURCE,
            "symbols": {s: e.stats() for s, e in self.engines.items()},
            "writer": {
                "written": self.writer.written if self.writer else 0,
                "failed_flushes": self.writer.failed_flushes if self.writer else 0,
                "queued": self.writer.queued if self.writer else 0,
            },
            "alerts": self.alert_evaluator.stats(),
            "backtests_running": self.backtests.running(),
            "ws": ws_manager.stats(),
        }


market_service = MarketService()
