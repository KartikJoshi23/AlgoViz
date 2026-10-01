"""Local order book — sync protocol, derived metrics, OFI."""

from __future__ import annotations

import math

from algoviz.market.book import LocalOrderBook
from algoviz.market.events import DepthDiffEvent, DepthSnapshotEvent

S = "BTCUSDT"


def snap(
    last_id: int, bids: list[tuple[float, float]], asks: list[tuple[float, float]]
) -> DepthSnapshotEvent:
    return DepthSnapshotEvent(S, 1_000, last_id, bids, asks)


def diff(
    U: int, u: int, bids: list[tuple[float, float]] = (), asks: list[tuple[float, float]] = ()
) -> DepthDiffEvent:  # type: ignore[assignment]
    return DepthDiffEvent(S, 2_000, U, u, list(bids), list(asks))


# ── Sync protocol ─────────────────────────────────────────────────


def test_diffs_before_snapshot_are_buffered_then_applied() -> None:
    b = LocalOrderBook(S)
    assert not b.apply_diff(diff(8, 9, bids=[(99.0, 1)]))  # buffered (state init)
    assert not b.apply_diff(diff(10, 12, bids=[(100.0, 5)]))  # covers lastUpdateId+1
    assert not b.apply_diff(diff(13, 13, asks=[(101.0, 2)]))
    b.apply_snapshot(snap(10, [(100.0, 1), (99.5, 2)], [(100.5, 1), (101.0, 1)]))
    assert b.synced
    # diff(8,9) dropped (u <= lastUpdateId); (10,12) applied; (13,13) applied
    assert b.last_update_id == 13
    assert b.best_bid == 100.0 and b._bids[-100.0] == 5
    assert b._asks[101.0] == 2


def test_first_diff_must_bracket_snapshot_id() -> None:
    b = LocalOrderBook(S)
    b.apply_snapshot(snap(100, [(10.0, 1)], [(11.0, 1)]))
    assert b.apply_diff(diff(95, 101, bids=[(10.0, 3)]))  # U <= 101 <= u
    assert b.last_update_id == 101
    assert b.apply_diff(diff(80, 90))  # stale → ignored but fine
    assert b.last_update_id == 101


def test_gap_triggers_resync_and_buffers_offending_diff() -> None:
    b = LocalOrderBook(S)
    b.apply_snapshot(snap(100, [(10.0, 1)], [(11.0, 1)]))
    assert b.apply_diff(diff(101, 103))
    assert not b.apply_diff(diff(110, 111, bids=[(9.0, 7)]))  # gap
    assert b.state == "syncing" and b.resyncs == 1 and b.needs_snapshot()
    # new snapshot beyond the gap → buffered diff (110,111) is dropped as stale
    b.apply_snapshot(snap(120, [(10.5, 1)], [(11.5, 1)]))
    assert b.synced and b.last_update_id == 120 and b.best_bid == 10.5
    assert b.apply_diff(diff(121, 121, asks=[(11.5, 0)]))  # remove level
    assert b.best_ask is None


def test_zero_qty_removes_levels_and_snapshot_resets() -> None:
    b = LocalOrderBook(S)
    b.apply_snapshot(snap(1, [(10.0, 1), (9.0, 1)], [(11.0, 1)]))
    assert b.apply_diff(diff(2, 2, bids=[(10.0, 0.0)]))
    assert b.best_bid == 9.0 and len(b) == 2
    b.apply_snapshot(snap(50, [(20.0, 1)], [(21.0, 1)]))
    assert len(b) == 2 and b.mid == 20.5


# ── Metrics ───────────────────────────────────────────────────────


def test_metrics_formulas() -> None:
    b = LocalOrderBook(S, weight_decay_bps=5.0, weight_band_bps=15.0)
    mid = 10_000.0
    b.apply_snapshot(
        snap(
            1,
            [(9_999.0, 3.0), (9_995.0, 1.0), (9_990.0, 2.0), (9_900.0, 100.0)],
            [(10_001.0, 1.0), (10_005.0, 1.0), (10_010.0, 2.0), (10_100.0, 100.0)],
        )
    )
    m = b.metrics(5)
    assert m is not None
    assert m.best_bid == 9_999.0 and m.best_ask == 10_001.0 and m.mid == mid
    assert math.isclose(m.spread_bps, 2 / mid * 10_000)
    assert math.isclose(m.microprice, (9_999.0 * 1.0 + 10_001.0 * 3.0) / 4.0)
    assert m.microprice_dev_bps > 0  # heavier bid ⇒ microprice above mid
    assert math.isclose(m.imbalance_l1, (3 - 1) / 4)
    # liquidity within 10 bps of 10 000 = [9990, 10010]: bids 3+1+2, asks 1+1+2
    assert math.isclose(m.liquidity_10bps, 10.0)
    assert math.isclose(m.liquidity_bid_10bps, 6.0) and math.isclose(m.liquidity_ask_10bps, 4.0)
    # the 100-lot walls at ±100 bps are outside every band
    assert math.isclose(m.liquidity_25bps, 10.0)
    assert math.isclose(m.slope_bid, 6.0 / 25.0)
    assert -1 <= m.imbalance_w <= 1 and m.imbalance_w > 0
    assert m.levels == 8
    bids, asks = b.top(2)
    assert bids == [(9_999.0, 3.0), (9_995.0, 1.0)] and asks[0] == (10_001.0, 1.0)


def test_weighted_imbalance_is_band_based_not_level_based() -> None:
    """A huge wall far outside the band must not dominate the weighted imbalance."""
    b = LocalOrderBook(S, weight_band_bps=15.0)
    b.apply_snapshot(snap(1, [(10_000.0, 1.0), (9_000.0, 1_000.0)], [(10_001.0, 1.0)]))
    m = b.metrics()
    assert m is not None and abs(m.imbalance_w) < 0.01


# ── OFI ───────────────────────────────────────────────────────────


def _book_at(bb: float, bq: float, ba: float, aq: float) -> LocalOrderBook:
    b = LocalOrderBook(S)
    b.apply_snapshot(snap(1, [(bb, bq)], [(ba, aq)]))
    return b


def test_ofi_bid_queue_grows_is_positive() -> None:
    b = _book_at(100.0, 1.0, 101.0, 1.0)
    assert b.apply_diff(diff(2, 2, bids=[(100.0, 3.0)]))
    # bid price unchanged: e = qb − qb' = 3 − 1 = +2 ; ask unchanged: −qa + qa' = 0
    assert math.isclose(b.take_ofi(), 2.0)
    assert b.take_ofi() == 0.0  # reset


def test_ofi_ask_lifted_is_positive_and_bid_hit_is_negative() -> None:
    b = _book_at(100.0, 1.0, 101.0, 4.0)
    # best ask moves up (queue at 101 consumed) → new best ask 102 with 2
    assert b.apply_diff(diff(2, 2, asks=[(101.0, 0.0), (102.0, 2.0)]))
    # ask: Pa=102 ≥ Pa'=101 → +qa' = +4 ; bid unchanged: +qb −qb' = 0 → e=+4
    assert math.isclose(b.take_ofi(), 4.0)
    # best bid moves down (hit) → new best bid 99
    assert b.apply_diff(diff(3, 3, bids=[(100.0, 0.0), (99.0, 5.0)]))
    # bid: Pb=99 ≤ Pb'=100 → −qb' = −1 ; ask unchanged → +qa' −qa = 0 → e=−1
    assert math.isclose(b.take_ofi(), -1.0)


def test_ofi_reference_resets_on_snapshot() -> None:
    b = _book_at(100.0, 1.0, 101.0, 1.0)
    b.apply_snapshot(snap(10, [(200.0, 9.0)], [(201.0, 9.0)]))
    assert b.take_ofi() == 0.0
    assert b.apply_diff(diff(11, 11, bids=[(200.0, 10.0)]))
    assert math.isclose(b.take_ofi(), 1.0)


def test_drain_gap_keeps_later_buffered_diffs_for_next_snapshot() -> None:
    """
    Regression: after a gap while draining, the diffs *after* the gap must stay
    buffered — the next snapshot may land inside their range. Dropping them made
    the following live diff gap again → resync storm.
    """
    b = LocalOrderBook(S)
    b.apply_diff(diff(101, 102, bids=[(10.0, 1)]))  # buffered (init)
    b.apply_diff(diff(110, 111, bids=[(10.0, 2)]))  # gap after the first one
    b.apply_diff(diff(112, 113, bids=[(10.0, 3)]))
    b.apply_snapshot(snap(100, [(9.0, 1)], [(11.0, 1)]))
    assert b.state == "syncing" and b.resyncs == 1
    assert [d.first_update_id for d in b._pending] == [110, 112]
    # snapshot inside the retained range → syncs and applies the rest
    b.apply_snapshot(snap(110, [(9.5, 1)], [(11.0, 1)]))
    assert b.synced and b.last_update_id == 113 and b._bids[-10.0] == 3


def test_depth_profile_bins_cumulative_from_mid_outward() -> None:
    b = LocalOrderBook(S)
    b.apply_snapshot(
        snap(
            1,
            [(9_999.0, 3.0), (9_995.0, 1.0), (9_990.0, 2.0), (9_900.0, 100.0)],
            [(10_001.0, 1.0), (10_005.0, 1.0), (10_010.0, 2.0), (10_100.0, 100.0)],
        )
    )
    # mid 10 000; 4 bins of 5 bps over a 20 bps band
    bids, asks = b.depth_profile(4, 20.0)
    # bin 0 = [0, 5) bps: 9 999 (1 bps) only — 9 995 sits exactly on 5 bps → bin 1
    assert bids == [3.0, 4.0, 6.0, 6.0]
    assert asks == [1.0, 2.0, 4.0, 4.0]
    assert b.depth_profile(0, 20.0) == ([], [])


def test_depth_reach_finds_the_offset_holding_most_of_the_depth() -> None:
    b = LocalOrderBook(S)
    b.apply_snapshot(
        snap(
            1,
            [(9_999.0, 3.0), (9_995.0, 1.0), (9_990.0, 2.0), (9_900.0, 100.0)],
            [(10_001.0, 1.0), (10_005.0, 1.0), (10_010.0, 2.0), (10_100.0, 100.0)],
        )
    )
    # within 25 bps: bids 3+1+2, asks 1+1+2 → 85 % of the bid side is reached at 9 990 (10 bps)
    assert b.depth_reach(0.85, 25.0) == 10.0
    # a tight reach: bids hit 40 % at the touch (1 bps) but asks need the 5 bps level;
    # the deeper side wins so the band covers both
    assert b.depth_reach(0.4, 25.0) == 5.0
    # the 100-lot walls dominate a 200 bps band: the reach jumps out to them
    assert b.depth_reach(0.85, 200.0) == 100.0
