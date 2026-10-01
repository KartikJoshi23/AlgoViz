"""Property tests — the book, the rolling windows and the bars against brute-force references."""

from __future__ import annotations

import math
from itertools import pairwise

from hypothesis import given, settings
from hypothesis import strategies as st

from algoviz.market.bars import BAR_MS, Bar, BarBuilder
from algoviz.market.book import LocalOrderBook
from algoviz.market.events import DepthDiffEvent, DepthSnapshotEvent, TradeEvent
from algoviz.market.ring import TimeWindowSum, TradeWindow

S = "BTCUSDT"
QTYS = (0.0, 0.0, 0.5, 1.0, 2.5)  # zero deletes the level, so deletes are common


# ── Order book sync ───────────────────────────────────────────────

levels = st.lists(
    st.tuples(st.sampled_from([100.0, 100.5, 101.0, 101.5, 102.0]), st.sampled_from(QTYS)),
    max_size=4,
)
asks = st.lists(
    st.tuples(st.sampled_from([103.0, 103.5, 104.0, 104.5, 105.0]), st.sampled_from(QTYS)),
    max_size=4,
)
update = st.tuples(st.integers(1, 3), levels, asks)  # (ids spanned, bid changes, ask changes)


def _diffs(updates: list[tuple[int, list, list]]) -> list[DepthDiffEvent]:
    out, next_id = [], 1
    for span, bids, asks_ in updates:
        out.append(DepthDiffEvent(S, next_id, next_id, next_id + span - 1, list(bids), list(asks_)))
        next_id += span
    return out


def _reference(
    diffs: list[DepthDiffEvent], upto: int
) -> tuple[dict[float, float], dict[float, float]]:
    """The true book after every diff whose ids end at or before `upto`."""
    bids: dict[float, float] = {}
    asks_: dict[float, float] = {}
    for d in diffs:
        if d.final_update_id > upto:
            break
        for side, changes in ((bids, d.bids), (asks_, d.asks)):
            for p, q in changes:
                if q > 0:
                    side[p] = q
                else:
                    side.pop(p, None)
    return bids, asks_


def _book(b: LocalOrderBook) -> tuple[dict[float, float], dict[float, float]]:
    bids, asks_ = b.top(10_000)
    return {p: q for p, q in bids}, {p: q for p, q in asks_}


@settings(max_examples=250, deadline=None)
@given(
    st.lists(update, min_size=1, max_size=30),
    st.data(),
)
def test_book_matches_the_reference_after_snapshot_buffer_and_redelivery(updates, data) -> None:  # type: ignore[no-untyped-def]
    diffs = _diffs(updates)
    last_id = diffs[-1].final_update_id
    snap_id = data.draw(st.integers(0, last_id), label="snapshot update id")
    # the snapshot arrives after every diff it covers, and maybe a few more
    arrive = next((i for i, d in enumerate(diffs) if d.final_update_id > snap_id), len(diffs))
    arrive = data.draw(st.integers(arrive, len(diffs)), label="diffs before the snapshot")
    book = LocalOrderBook(S)
    book.mark_syncing()
    for d in diffs[:arrive]:
        assert not book.apply_diff(d)  # buffered while syncing
    sb, sa = _reference(diffs, snap_id)
    book.apply_snapshot(DepthSnapshotEvent(S, 0, snap_id, sorted(sb.items()), sorted(sa.items())))
    for d in diffs[arrive:]:
        book.apply_diff(d)
        if data.draw(st.booleans(), label="redeliver"):
            assert book.apply_diff(d)  # a repeat is stale and ignored
    assert book.synced and book.last_update_id == last_id
    assert _book(book) == _reference(diffs, last_id)


@settings(max_examples=150, deadline=None)
@given(st.lists(update, min_size=3, max_size=20), st.data())
def test_a_lost_diff_is_detected_never_silently_applied_over(updates, data) -> None:  # type: ignore[no-untyped-def]
    diffs = _diffs(updates)
    lost = data.draw(st.integers(0, len(diffs) - 2), label="lost diff")
    book = LocalOrderBook(S)
    book.apply_snapshot(DepthSnapshotEvent(S, 0, 0))
    for i, d in enumerate(diffs):
        if i != lost:
            book.apply_diff(d)
        if book.synced:  # whenever it claims to be synced, it is right
            assert _book(book) == _reference(diffs, book.last_update_id)
    assert not book.synced and book.resyncs == 1


# ── Rolling windows ───────────────────────────────────────────────

trades = st.lists(
    st.tuples(
        st.integers(0, 3_000),  # ms since the previous trade
        st.floats(99, 101, allow_nan=False),
        st.floats(0.001, 5, allow_nan=False),
        st.booleans(),
    ),
    min_size=1,
    max_size=200,
)


@settings(max_examples=200, deadline=None)
@given(trades, st.sampled_from([1.0, 3.0, 30.0]))
def test_trade_window_matches_a_brute_force_window(ts, window_s) -> None:  # type: ignore[no-untyped-def]
    w = TradeWindow(window_s)
    sums = TimeWindowSum(window_s)
    seen: list[tuple[int, float, float, bool]] = []
    now = 0
    for dt, price, qty, is_buy in ts:
        now += dt
        w.push(now, price, qty, is_buy)
        sums.push(now, qty)
        seen.append((now, price, qty, is_buy))
        live = [r for r in seen if r[0] >= now - int(window_s * 1000)]
        vol = sum(r[2] for r in live)
        assert w.count == len(live) == sums.count
        assert math.isclose(w.volume, vol, rel_tol=1e-9, abs_tol=1e-9)
        assert math.isclose(sums.value, vol, rel_tol=1e-9, abs_tol=1e-9)
        assert math.isclose(
            w.buy_volume, sum(r[2] for r in live if r[3]), rel_tol=1e-9, abs_tol=1e-9
        )
        assert w.vwap is not None and math.isclose(
            w.vwap, sum(r[1] * r[2] for r in live) / vol, rel_tol=1e-9
        )


# ── Bars ──────────────────────────────────────────────────────────

ticks = st.lists(
    st.tuples(
        st.integers(0, 2_500),  # ms since the previous input
        st.booleans(),  # trade (True) or mid update
        st.floats(99, 101, allow_nan=False),
        st.floats(0.001, 3, allow_nan=False),
        st.booleans(),
    ),
    min_size=1,
    max_size=150,
)


@settings(max_examples=200, deadline=None)
@given(ticks)
def test_bars_are_contiguous_consistent_and_conserve_volume(inputs) -> None:  # type: ignore[no-untyped-def]
    closed: list[Bar] = []
    bb = BarBuilder(S, "test", closed.append)
    now, qty_total, n_trades = 1_000_000, 0.0, 0
    bb.on_mid(now, 100.0)
    for dt, is_trade, price, qty, maker in inputs:
        now += dt
        if is_trade:
            bb.on_trade(TradeEvent(S, now, price, qty, maker, n_trades))
            qty_total += qty
            n_trades += 1
        else:
            bb.on_mid(now, price)
    bb.flush(now + 2 * BAR_MS)  # closes everything that has ended
    assert closed, "at least one bar closed"
    for prev, bar in pairwise(closed):
        assert bar.ts_ms == prev.ts_ms + BAR_MS  # no gaps, no overlaps: empty seconds are bars too
    for bar in closed:
        assert bar.ts_ms % BAR_MS == 0
        assert bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
        assert 0 <= bar.buy_volume <= bar.volume + 1e-12
    assert math.isclose(sum(b.volume for b in closed), qty_total, rel_tol=1e-9, abs_tol=1e-9)
    assert sum(b.trade_count for b in closed) == n_trades
