"""
Synthetic source
================

A small but structurally honest limit-order-book simulator so the platform
runs, demos and trains without internet access:

- mid price: GBM with a 3-state sticky volatility chain and an OU drift that
  receives shocks on entering the high-vol state (so the HMM has regimes to
  find and "breakouts" actually exist);
- trades: self-exciting (Hawkes-style) intensity, side biased by book
  imbalance and drift, lognormal sizes, price impact;
- book: 25 levels per side on a tick grid around mid, mean-reverting queue
  sizes with noise, plus a sparse *far* layer out to ~30 bps whose resting
  size grows with distance and grows/loses walls at random (so liquidity
  bands, slopes and the depth terrain have structure); every 100 ms step
  emits a diff with proper `U`/`u` sequencing, and `request_snapshot()`
  emits a full snapshot.

Deterministic for a given seed; `speed` scales pacing (0 ⇒ as fast as possible).
"""

from __future__ import annotations

import asyncio
import logging
import math
import time

import numpy as np

from algoviz.market.events import (
    DepthDiffEvent,
    DepthSnapshotEvent,
    Level,
    SourceStatusEvent,
    TradeEvent,
)
from algoviz.market.sources import Emit, MarketSource

logger = logging.getLogger("algoviz.synthetic")

BASE_PRICES = {"BTCUSDT": 76_000.0, "ETHUSDT": 3_800.0, "SOLUSDT": 180.0}
TICKS = {"BTCUSDT": 0.1, "ETHUSDT": 0.01, "SOLUSDT": 0.001}
BASE_QTY = {"BTCUSDT": 0.35, "ETHUSDT": 6.0, "SOLUSDT": 120.0}

# per-100 ms return std in bps by vol state (≈ 4 / 7 / 22 bps per minute, i.e.
# roughly 25% / 50% / 150% annualised — calm, normal, and stressed BTC) and
# base trade intensity per step
_VOL_STATE_BPS = (0.15, 0.3, 0.9)
_INTENSITY = (0.8, 1.8, 4.5)
_STAY_PROB = 0.995
# Hawkes self-excitation: each trade adds ALPHA to the per-step intensity, which
# decays by exp(-DECAY) per step. Branching ratio ALPHA / (1 - exp(-DECAY)) must be
# < 1 or the process explodes; 0.05 / 0.095 ≈ 0.53.
_HAWKES_ALPHA = 0.05
_HAWKES_DECAY = 0.1
_MAX_INTENSITY = 40.0
# far layer: levels beyond the tick-grid band, spaced ever wider out to this offset
_FAR_MAX_BPS = 30.0
_WALL_BIRTH_PROB = 0.004  # per step, one side
_WALL_DECAY_PROB = 0.008  # per step, per active wall


class SyntheticSource(MarketSource):
    name = "synthetic"

    def __init__(
        self,
        symbol: str,
        *,
        seed: int = 42,
        speed: float = 1.0,
        step_ms: int = 100,
        levels: int = 25,
        far_levels: int = 24,
        base_price: float | None = None,
        start_ms: int | None = None,
    ) -> None:
        super().__init__(symbol)
        self._rng = np.random.RandomState(seed)
        self.speed = speed
        self.time_scale = speed  # 0 = unpaced (as fast as possible)
        self._step_ms = step_ms
        self._levels = levels
        self._tick = TICKS.get(self.symbol, 0.01)
        self._base_qty = BASE_QTY.get(self.symbol, 1.0)
        self._mid = base_price or BASE_PRICES.get(self.symbol, 100.0)
        self._vol_state = 1
        self._drift = 0.0
        self._excite = 0.0
        self._t_ms = start_ms if start_ms is not None else int(time.time() * 1000)
        self._update_id = 1_000
        self._trade_id = 1
        self._bid_q = np.zeros(levels)
        self._ask_q = np.zeros(levels)
        self._bid_px = np.zeros(levels)
        self._ask_px = np.zeros(levels)
        self._far = far_levels
        self._far_bid_px = np.zeros(far_levels)
        self._far_ask_px = np.zeros(far_levels)
        self._far_bid_q = np.zeros(far_levels)
        self._far_ask_q = np.zeros(far_levels)
        self._far_bid_mult = np.ones(far_levels)
        self._far_ask_mult = np.ones(far_levels)
        self._emit: Emit | None = None
        self._pending_snapshot = False
        self.steps = 0
        self._init_book()

    # ── Model ─────────────────────────────────────────────────────

    def now_ms(self) -> int:
        return self._t_ms

    def _round_tick(self, px: float, up: bool) -> float:
        n = px / self._tick
        return (math.ceil(n) if up else math.floor(n)) * self._tick

    def _target_qty(self, i: int) -> float:
        return self._base_qty * (1.0 + 0.8 * i / self._levels)

    def _far_target_qty(self, k: int) -> float:
        # resting size grows with distance from mid, as on real books
        return self._base_qty * (1.5 + 5.0 * (k + 1) / self._far)

    def _init_book(self) -> None:
        self._reprice()
        for i in range(self._levels):
            self._bid_q[i] = self._target_qty(i) * self._rng.lognormal(0, 0.35)
            self._ask_q[i] = self._target_qty(i) * self._rng.lognormal(0, 0.35)
        for k in range(self._far):
            self._far_bid_q[k] = self._far_target_qty(k) * self._rng.lognormal(0, 0.4)
            self._far_ask_q[k] = self._far_target_qty(k) * self._rng.lognormal(0, 0.4)

    def _reprice(self) -> None:
        half = max(1, self._vol_state + 1) * self._tick / 2  # spread widens with vol
        bb = self._round_tick(self._mid - half, up=False)
        ba = self._round_tick(self._mid + half, up=True)
        if ba <= bb:
            ba = bb + self._tick
        for i in range(self._levels):
            self._bid_px[i] = round(bb - i * self._tick, 8)
            self._ask_px[i] = round(ba + i * self._tick, 8)
        # far layer: offsets widen super-linearly from just past the tick grid
        near_bps = self._levels * self._tick / self._mid * 10_000
        prev_b, prev_a = float(self._bid_px[-1]), float(self._ask_px[-1])
        for k in range(self._far):
            off = near_bps + 0.2 + (_FAR_MAX_BPS - near_bps) * ((k + 1) / self._far) ** 1.5
            pb = min(self._round_tick(bb * (1 - off / 10_000), up=False), prev_b - self._tick)
            pa = max(self._round_tick(ba * (1 + off / 10_000), up=True), prev_a + self._tick)
            self._far_bid_px[k] = prev_b = round(pb, 8)
            self._far_ask_px[k] = prev_a = round(pa, 8)

    def _advance_state(self) -> None:
        rng = self._rng
        if rng.rand() > _STAY_PROB:
            nxt = self._vol_state + rng.choice((-1, 1))
            nxt = int(min(max(nxt, 0), 2))
            if nxt == 2 and self._vol_state != 2:
                self._drift += rng.choice((-1, 1)) * 1.5e-4  # breakout shock (per step)
            self._vol_state = nxt
        # OU drift (per-step return component)
        self._drift += -0.02 * self._drift + rng.normal(0, 4e-6)

    def _step_price(self, impact: float) -> None:
        sigma = _VOL_STATE_BPS[self._vol_state] / 10_000
        r = self._drift + sigma * self._rng.normal() + impact
        self._mid *= math.exp(r)

    def _imbalance(self) -> float:
        b, a = self._bid_q[:5].sum(), self._ask_q[:5].sum()
        return (b - a) / (b + a) if b + a > 0 else 0.0

    def _step_book(self) -> None:
        rng = self._rng
        for arr in (self._bid_q, self._ask_q):
            noise = rng.normal(0, 0.12, size=self._levels)
            targets = np.array([self._target_qty(i) for i in range(self._levels)])
            arr += 0.25 * (targets - arr) + noise * targets
            np.maximum(arr, 0.001, out=arr)
        # far layer: slow mean reversion around a target that walls can multiply
        far_targets = np.array([self._far_target_qty(k) for k in range(self._far)])
        for arr, mult in (
            (self._far_bid_q, self._far_bid_mult),
            (self._far_ask_q, self._far_ask_mult),
        ):
            if rng.rand() < _WALL_BIRTH_PROB:
                mult[rng.randint(self._far)] = rng.uniform(3.0, 7.0)
            active = mult > 1.0
            if active.any():
                decay = rng.rand(self._far) < _WALL_DECAY_PROB
                mult[active & decay] = 1.0
            targets = far_targets * mult
            arr += 0.05 * (targets - arr) + rng.normal(0, 0.03, size=self._far) * targets
            np.maximum(arr, 0.001, out=arr)

    def _trades(self, ts_ms: int) -> tuple[list[TradeEvent], float]:
        rng = self._rng
        lam = min(_INTENSITY[self._vol_state] + self._excite, _MAX_INTENSITY)
        n = int(rng.poisson(lam))
        self._excite *= math.exp(-_HAWKES_DECAY)
        events: list[TradeEvent] = []
        impact = 0.0
        imb = self._imbalance()
        p_buy = 1.0 / (1.0 + math.exp(-(2.0 * imb + 4000.0 * self._drift)))
        for k in range(n):
            is_buy = rng.rand() < p_buy
            qty = float(rng.lognormal(math.log(self._base_qty * 0.12), 0.9))
            if is_buy:
                px = float(self._ask_px[0])
                self._ask_q[0] = max(self._ask_q[0] - qty, 0.001)
            else:
                px = float(self._bid_px[0])
                self._bid_q[0] = max(self._bid_q[0] - qty, 0.001)
            impact += (1 if is_buy else -1) * min(qty / self._base_qty, 3.0) * 0.4e-5
            self._excite += _HAWKES_ALPHA
            events.append(
                TradeEvent(
                    symbol=self.symbol,
                    ts_ms=ts_ms + int(k * self._step_ms / max(n, 1)),
                    price=px,
                    qty=round(qty, 5),
                    is_buyer_maker=not is_buy,
                    trade_id=self._trade_id,
                )
            )
            self._trade_id += 1
        return events, impact

    def _all_levels(self) -> tuple[list[Level], list[Level]]:
        bids = [
            (float(p), round(float(q), 5)) for p, q in zip(self._bid_px, self._bid_q, strict=True)
        ]
        asks = [
            (float(p), round(float(q), 5)) for p, q in zip(self._ask_px, self._ask_q, strict=True)
        ]
        bids += [
            (float(p), round(float(q), 5))
            for p, q in zip(self._far_bid_px, self._far_bid_q, strict=True)
        ]
        asks += [
            (float(p), round(float(q), 5))
            for p, q in zip(self._far_ask_px, self._far_ask_q, strict=True)
        ]
        return bids, asks

    def _diff(self, ts_ms: int, prev_bid_px: np.ndarray, prev_ask_px: np.ndarray) -> DepthDiffEvent:
        bids, asks = self._all_levels()
        cur_b = {p for p, _ in bids}
        cur_a = {p for p, _ in asks}
        removed_b: list[Level] = [(float(p), 0.0) for p in prev_bid_px if float(p) not in cur_b]
        removed_a: list[Level] = [(float(p), 0.0) for p in prev_ask_px if float(p) not in cur_a]
        bids = removed_b + bids
        asks = removed_a + asks
        first = self._update_id + 1
        self._update_id += len(bids) + len(asks)
        return DepthDiffEvent(self.symbol, ts_ms, first, self._update_id, bids, asks)

    def snapshot(self) -> DepthSnapshotEvent:
        bids, asks = self._all_levels()
        return DepthSnapshotEvent(self.symbol, self._t_ms, self._update_id, bids, asks)

    # ── Source API ────────────────────────────────────────────────

    async def request_snapshot(self) -> None:
        self._pending_snapshot = True

    def step(self) -> list[TradeEvent | DepthDiffEvent | DepthSnapshotEvent]:
        """Advance one 100 ms step and return the events it produced (also used by tests)."""
        out: list[TradeEvent | DepthDiffEvent | DepthSnapshotEvent] = []
        if self._pending_snapshot:
            self._pending_snapshot = False
            out.append(self.snapshot())
        self._advance_state()
        trades, impact = self._trades(self._t_ms)
        out.extend(trades)
        prev_b = np.concatenate((self._bid_px, self._far_bid_px))
        prev_a = np.concatenate((self._ask_px, self._far_ask_px))
        self._step_price(impact)
        self._reprice()
        self._step_book()
        self._t_ms += self._step_ms
        out.append(self._diff(self._t_ms, prev_b, prev_a))
        self.steps += 1
        return out

    async def run(self, emit: Emit) -> None:
        self._emit = emit
        self.status = "connected"
        emit(SourceStatusEvent(self.symbol, self._t_ms, "connected", "synthetic"))
        emit(self.snapshot())
        step_s = self._step_ms / 1000.0 / self.speed if self.speed > 0 else 0.0
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        try:
            while True:
                for ev in self.step():
                    emit(ev)
                if step_s > 0:
                    # Paced against a deadline, not a fixed sleep: the step's own work and
                    # timer granularity (~15.6 ms on Windows) would otherwise stretch every
                    # step, and event time would fall steadily behind the wall clock.
                    deadline += step_s
                    await asyncio.sleep(max(0.0, deadline - loop.time()))
                elif self.steps % 10 == 0:  # one bar of event time per yield
                    await self.yield_to_consumer()
        finally:
            self.status = "stopped"

    def stats(self) -> dict[str, object]:
        return {
            **super().stats(),
            "steps": self.steps,
            "vol_state": self._vol_state,
            "mid": round(self._mid, 4),
        }
