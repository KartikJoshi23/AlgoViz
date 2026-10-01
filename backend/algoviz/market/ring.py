"""
Ring buffers and online accumulators
====================================

The O(1)-per-event primitives behind the streaming feature engine.

- `TradeWindow`     — time-windowed running sums over trades (Σpq, Σq, Σp, n,
                      buy volume) with Kahan-compensated accumulation and a
                      periodic exact recompute so float drift stays bounded
                      over days of uptime.
- `TimeWindowSum`   — the same idea for a single scalar series (OFI windows).
- `Ewm`             — irregular-interval exponentially weighted mean/variance
                      (half-life in seconds) for baselines and volatility.
- `RingBuffer`      — fixed-capacity numpy history with a monotonically
                      increasing head counter (the frontend mirrors this).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

_RECOMPUTE_EVERY = 4096  # evictions between exact recomputes (bounds Kahan residual)


class _KahanSum:
    """Compensated running sum supporting add and subtract."""

    __slots__ = ("_c", "_s")

    def __init__(self) -> None:
        self._s = 0.0
        self._c = 0.0

    def add(self, x: float) -> None:
        y = x - self._c
        t = self._s + y
        self._c = (t - self._s) - y
        self._s = t

    def sub(self, x: float) -> None:
        self.add(-x)

    def reset(self, value: float = 0.0) -> None:
        self._s, self._c = value, 0.0

    @property
    def value(self) -> float:
        return self._s


@dataclass(slots=True)
class _TradeRec:
    ts_ms: int
    price: float
    qty: float
    is_buy: bool


class TradeWindow:
    """
    Rolling time window over trades with O(1) amortised push/evict.

    `push()` appends and evicts expired records; `evict(now_ms)` can be
    called from a timer so a quiet market still decays the window.
    """

    __slots__ = (
        "_buy_qty",
        "_count",
        "_evictions",
        "_p",
        "_pq",
        "_q",
        "_recs",
        "window_ms",
    )

    def __init__(self, window_s: float) -> None:
        self.window_ms = int(window_s * 1000)
        self._recs: deque[_TradeRec] = deque()
        self._pq = _KahanSum()
        self._q = _KahanSum()
        self._p = _KahanSum()
        self._buy_qty = _KahanSum()
        self._count = 0
        self._evictions = 0

    def push(self, ts_ms: int, price: float, qty: float, is_buy: bool) -> None:
        self._recs.append(_TradeRec(ts_ms, price, qty, is_buy))
        self._pq.add(price * qty)
        self._q.add(qty)
        self._p.add(price)
        if is_buy:
            self._buy_qty.add(qty)
        self._count += 1
        self.evict(ts_ms)

    def evict(self, now_ms: int) -> None:
        cutoff = now_ms - self.window_ms
        recs = self._recs
        while recs and recs[0].ts_ms < cutoff:
            r = recs.popleft()
            self._pq.sub(r.price * r.qty)
            self._q.sub(r.qty)
            self._p.sub(r.price)
            if r.is_buy:
                self._buy_qty.sub(r.qty)
            self._count -= 1
            self._evictions += 1
        if not recs or self._evictions >= _RECOMPUTE_EVERY:
            self._recompute()

    def _recompute(self) -> None:
        self._evictions = 0
        pq = q = p = b = 0.0
        for r in self._recs:
            pq += r.price * r.qty
            q += r.qty
            p += r.price
            if r.is_buy:
                b += r.qty
        self._pq.reset(pq)
        self._q.reset(q)
        self._p.reset(p)
        self._buy_qty.reset(b)
        self._count = len(self._recs)

    # ── Derived values (all O(1)) ─────────────────────────────────

    @property
    def count(self) -> int:
        return self._count

    @property
    def volume(self) -> float:
        return max(self._q.value, 0.0)

    @property
    def buy_volume(self) -> float:
        return max(self._buy_qty.value, 0.0)

    @property
    def vwap(self) -> float | None:
        q = self._q.value
        return self._pq.value / q if q > 1e-12 else None

    @property
    def twap(self) -> float | None:
        return self._p.value / self._count if self._count else None

    @property
    def buy_pressure(self) -> float | None:
        q = self._q.value
        return self._buy_qty.value / q if q > 1e-12 else None

    def rate_per_s(self) -> float:
        """Trades per second over the window."""
        return self._count / (self.window_ms / 1000.0)

    @property
    def last(self) -> _TradeRec | None:
        return self._recs[-1] if self._recs else None


class TimeWindowSum:
    """Rolling time-windowed sum of a scalar series (O(1) amortised)."""

    __slots__ = ("_evictions", "_recs", "_sum", "window_ms")

    def __init__(self, window_s: float) -> None:
        self.window_ms = int(window_s * 1000)
        self._recs: deque[tuple[int, float]] = deque()
        self._sum = _KahanSum()
        self._evictions = 0

    def push(self, ts_ms: int, value: float) -> None:
        self._recs.append((ts_ms, value))
        self._sum.add(value)
        self.evict(ts_ms)

    def evict(self, now_ms: int) -> None:
        cutoff = now_ms - self.window_ms
        recs = self._recs
        while recs and recs[0][0] < cutoff:
            _, v = recs.popleft()
            self._sum.sub(v)
            self._evictions += 1
        if not recs or self._evictions >= _RECOMPUTE_EVERY:
            self._evictions = 0
            self._sum.reset(math.fsum(v for _, v in recs))

    @property
    def value(self) -> float:
        return self._sum.value

    @property
    def count(self) -> int:
        return len(self._recs)


class Ewm:
    """
    Exponentially weighted mean & variance for irregularly spaced samples.

    α = 1 − exp(−Δt / τ) with τ = half-life / ln 2, so a sample that arrives
    after a long gap carries more weight than one that arrives immediately.
    `n` counts samples for warm-up gating.
    """

    __slots__ = ("_last_ms", "_tau_ms", "mean", "n", "var")

    def __init__(self, halflife_s: float) -> None:
        self._tau_ms = halflife_s * 1000.0 / math.log(2.0)
        self.mean = 0.0
        self.var = 0.0
        self.n = 0
        self._last_ms: int | None = None

    def update(self, ts_ms: int, x: float) -> None:
        if not math.isfinite(x):
            return
        if self._last_ms is None:
            self.mean, self.var, self.n = x, 0.0, 1
            self._last_ms = ts_ms
            return
        dt = max(ts_ms - self._last_ms, 0)
        self._last_ms = ts_ms
        alpha = 1.0 - math.exp(-dt / self._tau_ms) if dt > 0 else 0.0
        # A zero-dt sample still contributes (alpha floor) so bursts are not ignored.
        alpha = max(alpha, 1e-4)
        delta = x - self.mean
        self.mean += alpha * delta
        self.var = (1.0 - alpha) * (self.var + alpha * delta * delta)
        self.n += 1

    @property
    def std(self) -> float:
        return math.sqrt(max(self.var, 0.0))

    def z(self, x: float, floor: float = 1e-9) -> float | None:
        if self.n < 2:
            return None
        return (x - self.mean) / max(self.std, floor)


class RingBuffer:
    """
    Fixed-capacity float64 history. `push()` is O(1); `view()` returns the
    values oldest→newest. `head` increases monotonically so consumers can
    detect new data without diffing arrays.
    """

    __slots__ = ("_buf", "_size", "capacity", "head")

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._buf = np.full(capacity, np.nan, dtype=np.float64)
        self._size = 0
        self.head = 0  # total pushes

    def push(self, value: float) -> None:
        self._buf[self.head % self.capacity] = value
        self.head += 1
        self._size = min(self._size + 1, self.capacity)

    def view(self) -> np.ndarray:
        if self._size < self.capacity:
            return self._buf[: self._size].copy()
        start = self.head % self.capacity
        return np.concatenate((self._buf[start:], self._buf[:start]))

    def last(self, n: int) -> np.ndarray:
        v = self.view()
        return v[-n:] if n < len(v) else v

    def __len__(self) -> int:
        return self._size

    @property
    def latest(self) -> float | None:
        if self._size == 0:
            return None
        return float(self._buf[(self.head - 1) % self.capacity])
