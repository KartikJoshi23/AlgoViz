"""Bars, streaming features, catalog sync, regime detector, synthetic source."""

from __future__ import annotations

import dataclasses
import math
from collections import Counter

import numpy as np
import pytest

from algoviz.config import Settings
from algoviz.market.bars import BAR_COLUMNS, REGIME_LABELS, TREND_LABELS, Bar, BarBuilder
from algoviz.market.book import LocalOrderBook
from algoviz.market.catalog import (
    FEATURE_REGISTRY,
    MODEL_FEATURES,
    catalog_payload,
    validate_condition,
)
from algoviz.market.events import DepthDiffEvent, DepthSnapshotEvent, TradeEvent
from algoviz.market.features import FeatureSnapshot, StreamingFeatureEngine
from algoviz.market.regime import LABELS, RegimeDetector, label_for_vol_z
from algoviz.market.synthetic import SyntheticSource

S = "BTCUSDT"
CFG = Settings(_env_file=None)  # type: ignore[call-arg]


def trade(ts_ms: int, price: float, qty: float, buy: bool, tid: int = 0) -> TradeEvent:
    return TradeEvent(S, ts_ms, price, qty, is_buyer_maker=not buy, trade_id=tid)


# ── Bars ──────────────────────────────────────────────────────────


def test_bars_close_on_event_time_and_carry_forward() -> None:
    closed: list[Bar] = []
    bb = BarBuilder(S, "test", closed.append)
    bb.on_mid(10_000, 100.0)
    bb.on_trade(trade(10_200, 100.5, 1.0, True))
    bb.on_mid(10_900, 101.0)
    assert closed == []  # still inside the 10 000–11 000 bar
    bb.on_mid(13_100, 102.0)  # jumps two full bars ahead
    assert [b.ts_ms for b in closed] == [10_000, 11_000, 12_000]
    first, empty1, empty2 = closed
    assert (first.open, first.high, first.low, first.close) == (100.0, 101.0, 100.0, 101.0)
    assert first.volume == 1.0 and first.buy_volume == 1.0 and first.trade_count == 1
    assert first.vwap_bar == 100.5
    # empty bars carry the last mid forward with zero volume
    assert empty1.open == empty1.close == 101.0 and empty1.volume == 0 and empty1.trade_count == 0
    assert empty2.close == 101.0


def test_bars_flush_closes_on_wall_clock() -> None:
    closed: list[Bar] = []
    bb = BarBuilder(S, "test", closed.append)
    bb.on_mid(5_000, 50.0)
    bb.flush(5_900)
    assert closed == []
    bb.flush(7_050)
    assert [b.ts_ms for b in closed] == [5_000, 6_000]
    assert bb.current_start == 7_000


def test_bar_compact_matches_columns() -> None:
    b = Bar(S, 0, "t", 1, 1, 1, 1, None, 0, 0, 0)
    assert len(b.compact()) == len(BAR_COLUMNS)


def test_bar_streams_the_regime_and_trend_as_ordinal_codes() -> None:
    col, tcol = BAR_COLUMNS.index("regime"), BAR_COLUMNS.index("trend")
    b = Bar(S, 0, "t", 1, 1, 1, 1, None, 0, 0, 0)
    assert b.compact()[col] is None and b.compact()[tcol] is None  # before the regime tier
    for code, label in enumerate(REGIME_LABELS):
        b.regime = label
        assert b.compact()[col] == code
    for code, label in enumerate(TREND_LABELS):
        b.trend = label
        assert b.compact()[tcol] == code


# ── Streaming features ────────────────────────────────────────────


def test_features_match_brute_force_windows() -> None:
    fe = StreamingFeatureEngine(S, CFG, "test")
    ts = 1_000_000
    trades = []
    for i in range(400):
        ts += 150
        t = trade(ts, 100 + (i % 7) * 0.1, 0.01 * (1 + i % 3), i % 3 != 0, i)
        trades.append(t)
        fe.on_trade(t)
    snap = fe.snapshot(ts)
    w = [t for t in trades if t.ts_ms >= ts - CFG.VWAP_WINDOW * 1000]
    q = sum(t.qty for t in w)
    assert snap.vwap is not None and math.isclose(snap.vwap, sum(t.price * t.qty for t in w) / q)
    assert snap.buy_pressure is not None
    assert math.isclose(snap.buy_pressure, sum(t.qty for t in w if not t.is_buyer_maker) / q)
    v = [t for t in trades if t.ts_ms >= ts - CFG.VELOCITY_WINDOW * 1000]
    assert math.isclose(snap.velocity, len(v) / CFG.VELOCITY_WINDOW)
    assert snap.trade_count_30s == len(w)
    assert snap.last_price == trades[-1].price
    assert snap.session_change_pct is not None


def test_features_from_book_and_z_warmup() -> None:
    fe = StreamingFeatureEngine(S, CFG, "test")
    book = LocalOrderBook(S)
    book.apply_snapshot(DepthSnapshotEvent(S, 1_000, 1, [(100.0, 2.0)], [(100.2, 1.0)]))
    fe.on_book(book, 1_000)
    s = fe.snapshot(1_000)
    assert s.mid == 100.1 and s.spread_bps is not None and s.spread_bps > 0
    assert s.microprice is not None and s.microprice > s.mid  # heavier bid
    assert s.spread_z is None and not s.warmed_up  # nothing warmed yet
    # feed bar closes across the warm-up window
    ts = 1_000
    for i in range(CFG.ZSCORE_WARMUP_S + 5):
        ts += 1_000
        assert book.apply_diff(DepthDiffEvent(S, ts, i + 2, i + 2, bids=[(100.0, 2.0 + (i % 3))]))
        fe.on_book(book, ts)
        fe.on_bar_close(ts, 100.1 + 0.01 * (i % 5))
    s = fe.snapshot(ts)
    assert s.warmed_up and s.spread_z is not None and s.ofi_z is not None
    assert s.volatility_bps is not None and s.volatility_bps >= 0
    assert s.velocity_baseline is not None


def test_snapshot_dict_matches_ws_features_payload() -> None:
    from algoviz.schemas.ws import FeaturesPayload

    fe = StreamingFeatureEngine(S, CFG, "test")
    d = fe.snapshot(0).to_dict()
    FeaturesPayload.model_validate(d)  # every field the contract declares is produced
    assert "current_price" not in d  # legacy keys are gone


# ── Catalog ↔ snapshot sync ───────────────────────────────────────


def test_catalog_names_are_produced_by_the_feature_snapshot() -> None:
    produced = {f.name for f in dataclasses.fields(FeatureSnapshot)}
    missing = [n for n in FEATURE_REGISTRY if n not in produced and n not in MODEL_FEATURES]
    assert missing == [], f"catalog names without a producer: {missing}"


def test_catalog_payload_and_validation() -> None:
    payload = catalog_payload()
    assert {p["name"] for p in payload} == set(FEATURE_REGISTRY)
    assert validate_condition("spread_z", "gt") is None
    assert validate_condition("regime", "in") is None
    assert "not valid" in (validate_condition("regime", "gt") or "")
    assert "unknown" in (validate_condition("nope", "gt") or "")


# ── Regime ────────────────────────────────────────────────────────


def _bar(ts: int, close: float, **kw: float | None) -> Bar:
    b = Bar(S, ts, "t", close, close, close, close, close, 0, 0, 0)
    for k, v in kw.items():
        setattr(b, k, v)
    return b


def test_label_thresholds() -> None:
    assert label_for_vol_z(-2.0) == "calm"
    assert label_for_vol_z(0.0) == "normal"
    assert label_for_vol_z(1.5) == "elevated"
    assert label_for_vol_z(3.0) == "extreme"


def test_regime_fallback_labels_before_fit() -> None:
    # the fallback uses the HMM's own cut-points: the volatility state only, whatever the flow
    rd = RegimeDetector(min_bars=1_000_000, min_dwell_bars=1)
    assert rd.push_bar(_bar(0, 100, vol_z=-1.0, ofi_z=0.1)).label == "calm"
    assert rd.push_bar(_bar(1000, 100, vol_z=0.5, ofi_z=3.0)).label == "normal"
    assert rd.push_bar(_bar(2000, 100, vol_z=1.8, ofi_z=0.0)).label == "elevated"
    st = rd.push_bar(_bar(3000, 100, vol_z=3.0, velocity_z=0.0, ofi_z=0.0))
    assert st.label == "extreme" and st.source == "fallback" and st.model_version == 0


def test_regime_min_dwell_prevents_flicker() -> None:
    rd = RegimeDetector(min_bars=1_000_000, min_dwell_bars=3)
    rd.push_bar(_bar(0, 100, vol_z=-1.0, ofi_z=0.0))
    assert rd.current().label == "calm"
    for i in range(2):  # two elevated bars are not enough
        rd.push_bar(_bar(1000 * (i + 1), 100, vol_z=2.0, ofi_z=0.0))
        assert rd.current().label == "calm"
    rd.push_bar(_bar(3000, 100, vol_z=2.0, ofi_z=0.0))
    assert rd.current().label == "elevated"


def test_regime_hmm_fit_and_decode_on_two_vol_regimes() -> None:
    rng = np.random.RandomState(0)
    # first fit after calm + stressed + calm blocks are all in the window
    rd = RegimeDetector(min_bars=650, refit_every_bars=10_000, window_bars=2_000, min_dwell_bars=1)
    price = 100.0
    ts = 0
    seen: list[str] = []
    for i in range(1_200):
        calm = (i // 300) % 2 == 0  # alternate calm / stressed blocks of 5 minutes
        sigma = 0.0002 if calm else 0.004
        vol_z = rng.normal(-0.6, 0.3) if calm else rng.normal(2.0, 0.5)
        price *= math.exp(rng.normal(0, sigma))
        ts += 1000
        bar = _bar(ts, price, spread_z=rng.normal(), ofi_z=rng.normal(), vol_z=vol_z)
        seen.append(rd.push_bar(bar).label)
        if rd.needs_refit():
            rd.install(RegimeDetector.fit(rd.training_matrix(), rd.model_version + 1))
    st = rd.current()
    assert st.source == "hmm" and st.model_version == 1
    assert set(st.probs) == set(LABELS) and math.isclose(sum(st.probs.values()), 1.0, abs_tol=1e-6)
    # blocks: 0–299 calm, 300–599 stressed, 600–899 calm, 900–1199 stressed (fit at bar 649)
    calm = Counter(seen[660:900])
    stressed = Counter(seen[910:1200])
    assert calm.most_common(1)[0][0] in ("calm", "normal"), calm
    assert stressed.most_common(1)[0][0] in ("elevated", "extreme"), stressed
    assert calm["calm"] + calm["normal"] > 0.9 * sum(calm.values())
    assert stressed["elevated"] + stressed["extreme"] > 0.9 * sum(stressed.values())


# ── Synthetic source ──────────────────────────────────────────────


def test_synthetic_is_deterministic_and_sequenced() -> None:
    a = SyntheticSource(S, seed=11, speed=0, start_ms=1_000_000)
    b = SyntheticSource(S, seed=11, speed=0, start_ms=1_000_000)
    ea = [e for _ in range(50) for e in a.step()]
    eb = [e for _ in range(50) for e in b.step()]
    assert [dataclasses.astuple(e) for e in ea] == [dataclasses.astuple(e) for e in eb]
    book = LocalOrderBook(S)
    book.apply_snapshot(a.snapshot())
    for _ in range(300):
        for e in a.step():
            if isinstance(e, DepthDiffEvent):
                assert book.apply_diff(e), "synthetic diffs must be gap-free"
    assert book.synced and book.resyncs == 0 and len(book) == 2 * (25 + 24)  # near + far layer
    assert any(isinstance(e, TradeEvent) for e in ea)
    # the far layer gives the liquidity bands structure: more within 25 bps than 5
    m = book.metrics()
    assert m is not None and m.liquidity_25bps > m.liquidity_10bps > m.liquidity_5bps > 0


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
def test_synthetic_prices_are_plausible(symbol: str) -> None:
    src = SyntheticSource(symbol, seed=1, speed=0)
    book = LocalOrderBook(symbol)
    book.apply_snapshot(src.snapshot())
    base = book.mid
    assert base is not None
    for _ in range(600):
        for e in src.step():
            if isinstance(e, DepthDiffEvent):
                book.apply_diff(e)
    mid = book.mid
    assert mid is not None and 0.8 * base < mid < 1.2 * base
    m = book.metrics()
    assert m is not None and 0 < m.spread_bps < 50
