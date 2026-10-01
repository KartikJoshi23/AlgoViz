"""
Local L2 order book
===================

Reconstructs the full limit order book from a REST snapshot plus the
`@depth@100ms` diff stream, following Binance's documented procedure:

1. buffer diffs while a snapshot is fetched;
2. drop diffs with `u <= lastUpdateId`;
3. the first applied diff must satisfy `U <= lastUpdateId + 1 <= u`;
4. every following diff must satisfy `U == prev_u + 1`, else resync.

Per update the book derives the microstructure quantities the engine and the
3D terrain consume: best quotes, mid, spread, **microprice**, depth-weighted
imbalance, liquidity within N bps, book slope, and accumulates **order-flow
imbalance** (Cont, Kukanov & Stoikov 2014) from best-level changes.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Literal

from sortedcontainers import SortedDict

from algoviz.market.events import DepthDiffEvent, DepthSnapshotEvent, Level

SyncState = Literal["init", "syncing", "synced"]


@dataclass(slots=True)
class BookMetrics:
    ts_ms: int
    best_bid: float
    best_ask: float
    bid_qty: float  # L1 quantities
    ask_qty: float
    mid: float
    spread: float
    spread_bps: float
    microprice: float
    microprice_dev_bps: float  # (microprice − mid) / mid, in bps
    imbalance_l1: float  # (bid − ask) / (bid + ask) at best level
    imbalance_w: float  # depth-weighted, exponential decay by distance
    liquidity_5bps: float  # bid + ask quantity within ±5 bps of mid
    liquidity_10bps: float
    liquidity_25bps: float
    liquidity_bid_10bps: float
    liquidity_ask_10bps: float
    slope_bid: float  # cumulative depth per bps (first 25 bps)
    slope_ask: float
    levels: int


class LocalOrderBook:
    def __init__(
        self,
        symbol: str,
        *,
        weight_decay_bps: float = 5.0,
        weight_band_bps: float = 15.0,
        weight_max_levels: int = 400,
    ) -> None:
        self.symbol = symbol
        # bids keyed by -price so iteration is best→worst; asks by price.
        self._bids: SortedDict[float, float] = SortedDict()
        self._asks: SortedDict[float, float] = SortedDict()
        self._pending: deque[DepthDiffEvent] = deque(maxlen=5000)
        self.state: SyncState = "init"
        self.last_update_id = 0
        self.last_ts_ms = 0
        self.resyncs = 0
        self.updates_applied = 0
        self._weight_decay_bps = weight_decay_bps
        self._weight_band_bps = weight_band_bps
        self._weight_max_levels = weight_max_levels
        # OFI accumulation
        self._ofi_acc = 0.0
        self._prev_bb: float | None = None
        self._prev_bq = 0.0
        self._prev_ba: float | None = None
        self._prev_aq = 0.0

    # ── Sync protocol ─────────────────────────────────────────────

    @property
    def synced(self) -> bool:
        return self.state == "synced"

    def needs_snapshot(self) -> bool:
        return self.state != "synced"

    def mark_syncing(self) -> None:
        if self.state != "syncing":
            self.state = "syncing"

    def apply_snapshot(self, snap: DepthSnapshotEvent) -> None:
        """Replace the book and drain buffered diffs newer than the snapshot."""
        self._bids.clear()
        self._asks.clear()
        for p, q in snap.bids:
            if q > 0:
                self._bids[-p] = q
        for p, q in snap.asks:
            if q > 0:
                self._asks[p] = q
        self.last_update_id = snap.last_update_id
        self.last_ts_ms = snap.ts_ms
        self.state = "synced"
        self._reset_ofi_reference()

        pending, self._pending = list(self._pending), deque(maxlen=5000)
        for i, diff in enumerate(pending):
            if diff.final_update_id <= snap.last_update_id:
                continue
            if not self.apply_diff(diff):
                # apply_diff flipped state to syncing and kept `diff`; keep the diffs
                # after it too — the next snapshot may land inside their range.
                self._pending.extend(pending[i + 1 :])
                break

    def apply_diff(self, diff: DepthDiffEvent) -> bool:
        """
        Apply a diff. Returns False when the book is not synced (diff buffered)
        or a sequence gap was detected (state → syncing; caller requests a
        snapshot).
        """
        if self.state != "synced":
            self._pending.append(diff)
            return False
        if diff.final_update_id <= self.last_update_id:
            return True  # stale, already covered
        expected = self.last_update_id + 1
        if not (diff.first_update_id <= expected <= diff.final_update_id):
            # Gap → discard book and go back to syncing with this diff buffered.
            self.state = "syncing"
            self.resyncs += 1
            self._pending.clear()
            self._pending.append(diff)
            return False

        for p, q in diff.bids:
            k = -p
            if q <= 0:
                self._bids.pop(k, None)
            else:
                self._bids[k] = q
        for p, q in diff.asks:
            if q <= 0:
                self._asks.pop(p, None)
            else:
                self._asks[p] = q

        self.last_update_id = diff.final_update_id
        self.last_ts_ms = diff.ts_ms
        self.updates_applied += 1
        self._accumulate_ofi()
        return True

    # ── OFI ───────────────────────────────────────────────────────

    def _reset_ofi_reference(self) -> None:
        bb, bq = self._best(self._bids, negate=True)
        ba, aq = self._best(self._asks)
        self._prev_bb, self._prev_bq, self._prev_ba, self._prev_aq = bb, bq, ba, aq

    def _accumulate_ofi(self) -> None:
        """
        e_n = 1{Pb ≥ Pb'} qb − 1{Pb ≤ Pb'} qb'  −  1{Pa ≤ Pa'} qa + 1{Pa ≥ Pa'} qa'
        (primes are previous best level values). Positive ⇒ net buying pressure.
        """
        bb, bq = self._best(self._bids, negate=True)
        ba, aq = self._best(self._asks)
        if bb is None or ba is None:
            return
        pbb, pba = self._prev_bb, self._prev_ba
        if pbb is not None and pba is not None:
            e = 0.0
            if bb >= pbb:
                e += bq
            if bb <= pbb:
                e -= self._prev_bq
            if ba <= pba:
                e -= aq
            if ba >= pba:
                e += self._prev_aq
            self._ofi_acc += e
        self._prev_bb, self._prev_bq, self._prev_ba, self._prev_aq = bb, bq, ba, aq

    def take_ofi(self) -> float:
        """Return accumulated OFI since the last call and reset it."""
        v, self._ofi_acc = self._ofi_acc, 0.0
        return v

    @property
    def ofi_pending(self) -> float:
        return self._ofi_acc

    # ── Reads ─────────────────────────────────────────────────────

    @staticmethod
    def _best(side: SortedDict, negate: bool = False) -> tuple[float | None, float]:
        if not side:
            return None, 0.0
        k, q = side.peekitem(0)
        return (-k if negate else k), q

    @property
    def best_bid(self) -> float | None:
        return self._best(self._bids, negate=True)[0]

    @property
    def best_ask(self) -> float | None:
        return self._best(self._asks)[0]

    @property
    def mid(self) -> float | None:
        bb, ba = self.best_bid, self.best_ask
        return (bb + ba) / 2.0 if bb is not None and ba is not None else None

    def top(self, n: int) -> tuple[list[Level], list[Level]]:
        bids = [(-k, q) for k, q in self._bids.items()[:n]]
        asks = [(k, q) for k, q in self._asks.items()[:n]]
        return bids, asks

    def depth_within_bps(self, bps: float) -> tuple[float, float]:
        mid = self.mid
        if mid is None:
            return 0.0, 0.0
        # Inclusive band with a relative epsilon so a level sitting exactly on the
        # boundary is not excluded by floating-point rounding.
        lo, hi = mid * (1 - bps / 10_000) * (1 - 1e-12), mid * (1 + bps / 10_000) * (1 + 1e-12)
        bid_qty = 0.0
        for k, q in self._bids.items():
            if -k < lo:
                break
            bid_qty += q
        ask_qty = 0.0
        for k, q in self._asks.items():
            if k > hi:
                break
            ask_qty += q
        return bid_qty, ask_qty

    def depth_profile(self, bins: int, band_bps: float) -> tuple[list[float], list[float]]:
        """
        Cumulative resting quantity per price bin, from mid outward, for each side.

        Bin ``i`` covers offsets ``[i·step, (i+1)·step)`` bps from mid with
        ``step = band_bps / bins``; its value is the total quantity resting at or
        nearer than the far edge of the bin. Built from the *full* local book, so
        the terrain sees the whole band even though the level list is capped.
        """
        mid = self.mid
        if mid is None or bins <= 0 or band_bps <= 0:
            return [], []
        step = band_bps / bins
        lim = band_bps * (1 + 1e-12)

        def scan(side: SortedDict, negate: bool) -> list[float]:
            out = [0.0] * bins
            cum = 0.0
            b = 0
            for k, q in side.items():
                price = -k if negate else k
                d = abs(price - mid) / mid * 10_000
                if d > lim:
                    break
                idx = min(int(d / step), bins - 1)
                while b < idx:  # bins nearer than this level are final
                    out[b] = cum
                    b += 1
                cum += q
            while b < bins:
                out[b] = cum
                b += 1
            return out

        return scan(self._bids, True), scan(self._asks, False)

    def depth_reach(self, fraction: float, max_bps: float) -> float:
        """
        Offset (bps from mid) within which `fraction` of the resting quantity
        found inside `max_bps` sits, on the deeper side. Used to size the
        depth-profile band to the instrument: a BTC book saturates within a few
        bps while a thin altcoin book needs the whole 25 bps.
        """
        mid = self.mid
        if mid is None or max_bps <= 0:
            return max_bps
        lim = max_bps * (1 + 1e-12)

        def reach(side: SortedDict, negate: bool) -> float:
            total = 0.0
            offsets: list[tuple[float, float]] = []
            for k, q in side.items():
                price = -k if negate else k
                d = abs(price - mid) / mid * 10_000
                if d > lim:
                    break
                total += q
                offsets.append((d, q))
            if total <= 0:
                return 0.0
            cum = 0.0
            for d, q in offsets:
                cum += q
                if cum >= fraction * total:
                    return d
            return max_bps

        return max(reach(self._bids, True), reach(self._asks, False))

    def prune(self, max_bps: float) -> int:
        """
        Drop levels farther than `max_bps` from mid; returns how many. Diffs keep
        adding every price ever touched, so an unpruned book grows all day while
        nothing past 25 bps is ever read.
        """
        mid = self.mid
        if mid is None or max_bps <= 0:
            return 0
        lo, hi = mid * (1 - max_bps / 10_000), mid * (1 + max_bps / 10_000)
        far_bids = list(self._bids.islice(self._bids.bisect_right(-lo)))  # keys are −price
        far_asks = list(self._asks.islice(self._asks.bisect_right(hi)))
        for k in far_bids:
            del self._bids[k]
        for k in far_asks:
            del self._asks[k]
        return len(far_bids) + len(far_asks)

    def metrics(self, ts_ms: int | None = None) -> BookMetrics | None:
        bb, bq = self._best(self._bids, negate=True)
        ba, aq = self._best(self._asks)
        if bb is None or ba is None or ba <= 0:
            return None
        mid = (bb + ba) / 2.0
        spread = ba - bb
        spread_bps = spread / mid * 10_000 if mid > 0 else 0.0
        denom = bq + aq
        microprice = (bb * aq + ba * bq) / denom if denom > 0 else mid
        imb_l1 = (bq - aq) / denom if denom > 0 else 0.0
        b5, b10, b25, wb_num, wb_den = self._scan_side(self._bids, mid, negate=True)
        a5, a10, a25, wa_num, wa_den = self._scan_side(self._asks, mid, negate=False)
        w_den = wb_den + wa_den
        imb_w = (wb_num - wa_num) / w_den if w_den > 0 else 0.0
        return BookMetrics(
            ts_ms=ts_ms if ts_ms is not None else self.last_ts_ms,
            best_bid=bb,
            best_ask=ba,
            bid_qty=bq,
            ask_qty=aq,
            mid=mid,
            spread=spread,
            spread_bps=spread_bps,
            microprice=microprice,
            microprice_dev_bps=(microprice - mid) / mid * 10_000 if mid > 0 else 0.0,
            imbalance_l1=imb_l1,
            imbalance_w=imb_w,
            liquidity_5bps=b5 + a5,
            liquidity_10bps=b10 + a10,
            liquidity_25bps=b25 + a25,
            liquidity_bid_10bps=b10,
            liquidity_ask_10bps=a10,
            slope_bid=b25 / 25.0,
            slope_ask=a25 / 25.0,
            levels=len(self._bids) + len(self._asks),
        )

    def _scan_side(
        self, side: SortedDict, mid: float, *, negate: bool
    ) -> tuple[float, float, float, float, float]:
        """
        One ordered pass from the best level outward, accumulating resting quantity
        within 5 / 10 / 25 bps of mid and the exponentially weighted sums used by the
        weighted imbalance (band `weight_band_bps`, capped at `weight_max_levels`).
        """
        if mid <= 0:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        eps = 1e-12
        lim5, lim10, lim25 = 5 * (1 + eps), 10 * (1 + eps), 25 * (1 + eps)
        decay, band, cap = self._weight_decay_bps, self._weight_band_bps, self._weight_max_levels
        q5 = q10 = q25 = w_num = w_den = 0.0
        for i, (k, q) in enumerate(side.items()):
            price = -k if negate else k
            d = abs(price - mid) / mid * 10_000
            if d > lim25:
                break
            q25 += q
            if d <= lim10:
                q10 += q
                if d <= lim5:
                    q5 += q
            if d <= band and i < cap:
                w = math.exp(-d / decay)
                w_num += w * q
                w_den += w * q
        return q5, q10, q25, w_num, w_den

    def __len__(self) -> int:
        return len(self._bids) + len(self._asks)
