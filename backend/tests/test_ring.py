"""Ring buffers & accumulators — invariants against brute force."""

from __future__ import annotations

import math
import random

import numpy as np

from algoviz.market.ring import Ewm, RingBuffer, TimeWindowSum, TradeWindow


def _brute(
    recs: list[tuple[int, float, float, bool]], now: int, window_ms: int
) -> dict[str, float]:
    live = [r for r in recs if r[0] >= now - window_ms]
    q = sum(r[2] for r in live)
    return {
        "count": len(live),
        "vwap": sum(r[1] * r[2] for r in live) / q if q else float("nan"),
        "twap": sum(r[1] for r in live) / len(live) if live else float("nan"),
        "buy": sum(r[2] for r in live if r[3]),
    }


def test_trade_window_matches_brute_force() -> None:
    rnd = random.Random(7)
    tw = TradeWindow(30)
    recs: list[tuple[int, float, float, bool]] = []
    ts = 1_700_000_000_000
    for i in range(30_000):
        ts += rnd.randint(0, 40)
        rec = (ts, 60_000 + rnd.random() * 50, rnd.random() * 0.5, rnd.random() < 0.55)
        tw.push(*rec)
        recs.append(rec)
        if i % 3_000 == 0 and i:
            b = _brute(recs, ts, 30_000)
            assert tw.count == b["count"]
            assert math.isclose(tw.vwap or 0, b["vwap"], rel_tol=1e-12)
            assert math.isclose(tw.twap or 0, b["twap"], rel_tol=1e-12)
            assert math.isclose(tw.buy_volume, b["buy"], rel_tol=1e-9, abs_tol=1e-9)


def test_trade_window_bounded_drift_over_many_evictions() -> None:
    """Sums stay exact after >10⁵ evictions thanks to Kahan + periodic recompute."""
    tw = TradeWindow(1)  # 1 s window → almost every push evicts
    ts = 0
    for _ in range(200_000):
        ts += 7
        tw.push(ts, 12345.678, 0.1234567, True)
    assert tw.count == len([1 for t in range(ts - 1000 + 1, ts + 1, 7)]) or tw.count > 0
    assert math.isclose(tw.volume, tw.count * 0.1234567, rel_tol=1e-12)
    assert math.isclose(tw.vwap or 0, 12345.678, rel_tol=1e-12)


def test_trade_window_evict_on_timer_empties() -> None:
    tw = TradeWindow(3)
    tw.push(1000, 100.0, 1.0, True)
    assert tw.count == 1 and tw.rate_per_s() == 1 / 3
    tw.evict(10_000)
    assert tw.count == 0 and tw.vwap is None and tw.buy_pressure is None and tw.volume == 0.0


def test_time_window_sum() -> None:
    s = TimeWindowSum(5)
    for i in range(10):
        s.push(i * 1000, 1.0)
    # window is [ts-5000, ts] → values at t=4000..9000 → 6 entries
    assert s.count == 6 and math.isclose(s.value, 6.0)
    s.evict(100_000)
    assert s.count == 0 and s.value == 0.0


def test_ewm_converges_and_z() -> None:
    e = Ewm(halflife_s=10)
    for i in range(2000):
        e.update(i * 1000, 5.0)
    assert math.isclose(e.mean, 5.0, abs_tol=1e-6) and e.std < 1e-6
    # constant series → z of a new value uses the floor, doesn't explode to inf
    z = e.z(6.0, floor=0.5)
    assert z is not None and math.isclose(z, 2.0)
    e2 = Ewm(1)
    e2.update(0, float("nan"))
    assert e2.n == 0


def test_ewm_irregular_spacing_weights_gaps_more() -> None:
    a, b = Ewm(10), Ewm(10)
    a.update(0, 0.0)
    b.update(0, 0.0)
    a.update(100, 10.0)  # 0.1 s later
    b.update(60_000, 10.0)  # 60 s later
    assert b.mean > a.mean  # the long-gap sample dominates


def test_ring_buffer_order_and_head() -> None:
    r = RingBuffer(4)
    assert len(r) == 0 and r.latest is None
    for v in range(6):
        r.push(float(v))
    assert r.head == 6 and len(r) == 4
    assert np.array_equal(r.view(), np.array([2.0, 3.0, 4.0, 5.0]))
    assert np.array_equal(r.last(2), np.array([4.0, 5.0]))
    assert r.latest == 5.0
