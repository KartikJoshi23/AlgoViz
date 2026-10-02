"""Stage C unit tests — conditions, signals, labels, training, drift, backtest engine."""

from __future__ import annotations

import asyncio
import math
from itertools import pairwise

import numpy as np
import pytest
from pydantic import ValidationError

from algoviz.alerts.templates import render, template_error
from algoviz.backtest.engine import run_backtest
from algoviz.backtest.metrics import max_drawdown_pct, sharpe_sortino
from algoviz.backtest.service import generate_synthetic_bars
from algoviz.backtest.strategy import EXAMPLE_SPECS, StrategySpec
from algoviz.core.conditions import Cond, Group, parse_condition
from algoviz.market.bars import Bar
from algoviz.ml.drift import DriftMonitor, Outcome
from algoviz.ml.features import FEATURE_NAMES, LOOKBACK, N_FEATURES, feature_vector
from algoviz.ml.labels import CLASS_DOWN, CLASS_FLAT, CLASS_UP, barrier_bps, triple_barrier
from algoviz.ml.train import train
from algoviz.signals.engine import SignalEngine
from algoviz.signals.rules import DEFAULT_RULES, SignalRule

S = "BTCUSDT"


pytestmark = pytest.mark.usefixtures("capped_threads")


def _bar(i: int, close: float, **kw: object) -> Bar:
    b = Bar(
        S,
        1_700_000_000_000 + i * 1000,
        "t",
        close,
        close * 1.0002,
        close * 0.9998,
        close,
        close,
        1.0,
        0.5,
        5,
    )
    for k, v in kw.items():
        setattr(b, k, v)
    return b


# ── Conditions ────────────────────────────────────────────────────


def test_condition_language_and_validation() -> None:
    g = parse_condition(
        {
            "all": [
                {"f": "ofi_z", "op": "gt", "v": 1.5},
                {"not": {"f": "regime", "op": "==", "v": "calm"}},
            ]
        }
    )
    assert isinstance(g, Group)
    assert g.evaluate({"ofi_z": 2.0, "regime": "normal"})
    assert not g.evaluate({"ofi_z": 2.0, "regime": "calm"})
    assert not g.evaluate({"ofi_z": None, "regime": "normal"})  # missing → false, never an error
    assert g.fields() == {"ofi_z", "regime"}
    for bad in (
        {"f": "nope", "op": ">", "v": 1},
        {"f": "regime", "op": ">", "v": 1},
        {"f": "regime", "op": "in", "v": ["trending"]},  # a trend is not a volatility state
        {"f": "trend", "op": "==", "v": "sideways"},
        {"f": "spread_z", "op": "in", "v": 1},
        {"f": "spread_z", "op": ">", "v": "high"},
        {"all": []},
        {
            "all": [{"f": "spread_z", "op": ">", "v": 1}],
            "any": [{"f": "spread_z", "op": ">", "v": 1}],
        },
    ):
        with pytest.raises(ValidationError):
            parse_condition(bad)
    assert Cond(f="bars_held", op=">=", v=10).evaluate({"bars_held": 12})  # context field


# ── Signals ───────────────────────────────────────────────────────


def _ctx(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "spread_z": 0.0, "spread_bps": 0.01, "vol_z": 0.0, "volatility_bps": 5.0, "ofi_z": 0.0,
        "imbalance_w": 0.0, "imbalance_l1": 0.0, "velocity_z": 0.0, "velocity": 10.0,
        "liquidity_z": 0.0, "liquidity_10bps": 50.0, "regime": "normal", "regime_direction": 0.0,
        "trend": "flat",
        "p_up": None, "p_down": None,
    }  # fmt: skip
    base.update(kw)
    return base


def test_default_rules_are_valid_and_quiet_at_baseline() -> None:
    eng = SignalEngine(DEFAULT_RULES)
    assert len(eng.rules) == len(DEFAULT_RULES) >= 14
    assert eng.evaluate(_ctx(), 1_000) == []
    assert eng.active(1_000) == []


def test_signal_hysteresis_min_duration_and_cooldown() -> None:
    rule = SignalRule(
        id="t", name="T", enter=Cond(f="spread_z", op=">", v=2.0), exit=Cond(f="spread_z", op="<", v=1.0),
        min_duration_s=2, cooldown_s=10, message="z={spread_z:.1f}",
    )  # fmt: skip
    eng = SignalEngine([rule])
    t = eng.evaluate(_ctx(spread_z=2.5), 1_000)
    assert [x.kind for x in t] == ["activated"] and t[0].signal.message == "z=2.5"
    assert eng.evaluate(_ctx(spread_z=1.5), 2_000) == []  # between exit and enter: stays active
    assert eng.evaluate(_ctx(spread_z=0.5), 2_500) == []  # exit true but < min_duration
    t = eng.evaluate(_ctx(spread_z=0.5), 3_100)
    assert [x.kind for x in t] == ["deactivated"] and t[0].duration_s == 2.1
    assert eng.evaluate(_ctx(spread_z=3.0), 5_000) == []  # cooldown (10 s) blocks re-entry
    assert [x.kind for x in eng.evaluate(_ctx(spread_z=3.0), 14_000)] == ["activated"]
    assert len(eng.recent()) == 3 and eng.recent()[0]["kind"] == "activated"


def test_calm_signal_clears_when_the_market_is_no_longer_calm() -> None:
    rule = next(r for r in DEFAULT_RULES if r.id == "vol_calm")
    eng = SignalEngine([rule])
    assert [t.kind for t in eng.evaluate(_ctx(regime="calm"), 1_000)] == ["activated"]
    assert [t.kind for t in eng.evaluate(_ctx(regime="normal"), 40_000)] == ["deactivated"]


def test_trend_signals_follow_the_trend_not_the_volatility_state() -> None:
    eng = SignalEngine([r for r in DEFAULT_RULES if r.id in ("trend_up", "trend_down")])
    assert eng.evaluate(_ctx(regime="extreme", trend="flat"), 1_000) == []  # wild but no drift
    t = eng.evaluate(_ctx(regime="calm", trend="up", regime_direction=0.8), 2_000)
    assert [(x.kind, x.signal.rule_id) for x in t] == [("activated", "trend_up")]


def test_signal_rule_message_tolerates_missing_values() -> None:
    rule = SignalRule(
        id="m", name="M", enter=Cond(f="vol_z", op=">", v=1), exit=Cond(f="vol_z", op="<", v=0),
        message="vol {vol_z:.1f} missing {nothing}",
    )  # fmt: skip
    assert rule.render({"vol_z": 1.5}) == "vol 1.5 missing ?"


# ── Labels ────────────────────────────────────────────────────────


def test_triple_barrier_first_touch_and_timeout() -> None:
    closes = [100.0, 100.01, 100.05, 99.9, 100.2, 100.3]
    up = triple_barrier(closes, 0, horizon=5, barrier=4.0)  # +4 bps
    assert (
        up
        and up.cls == CLASS_UP
        and up.bars_to_touch == 2
        and math.isclose(up.realised_bps, 5.0, abs_tol=1e-9)
    )
    dn = triple_barrier(closes, 0, horizon=5, barrier=6.0)
    assert (
        dn and dn.cls == CLASS_DOWN and dn.bars_to_touch == 3
    )  # −10 bps at index 3 before +20 at 4
    flat = triple_barrier(closes, 0, horizon=2, barrier=10.0)
    assert (
        flat
        and flat.cls == CLASS_FLAT
        and flat.bars_to_touch == 2
        and math.isclose(flat.realised_bps, 5.0, abs_tol=1e-9)
    )
    assert triple_barrier(closes, 3, horizon=5, barrier=1.0) is None  # incomplete path


def test_barrier_is_volatility_scaled_with_floor() -> None:
    assert barrier_bps(None, 5, 1.0, 0.5) == 0.5
    assert math.isclose(barrier_bps(6.0, 5, 1.0, 0.5), 6.0 * math.sqrt(5 / 60))
    assert barrier_bps(0.1, 5, 1.0, 0.5) == 0.5


# ── Features ──────────────────────────────────────────────────────


def test_feature_vector_shape_and_names() -> None:
    assert len(FEATURE_NAMES) == N_FEATURES == len(set(FEATURE_NAMES))
    bars = [
        _bar(i, 100 + 0.01 * i, spread_bps=0.01, regime="normal", vol_z=0.5)
        for i in range(LOOKBACK)
    ]
    assert feature_vector(bars[:-1], (1.0, 1.0, 1.0)) is None
    v = feature_vector(bars, (1.0, 1.0, 1.0))
    assert v is not None and v.shape == (N_FEATURES,) and np.all(np.isfinite(v))
    names = dict(zip(FEATURE_NAMES, v, strict=True))
    assert names["regime_normal"] == 1.0 and names["regime_calm"] == 0.0
    assert names["consec_up"] >= 19 and names["ret_1"] > 0


# ── Training ──────────────────────────────────────────────────────


def _synthetic_dataset(n: int, informative: bool, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(seed)
    X = rng.normal(size=(n, N_FEATURES))
    if informative:
        score = 1.5 * X[:, 0] - 1.0 * X[:, 5] + rng.normal(scale=0.5, size=n)
        y = np.where(score > 0.8, 2, np.where(score < -0.8, 0, 1))
    else:
        y = rng.randint(0, 3, size=n)
    return X, y


def test_training_reports_edge_on_informative_data_and_none_on_noise() -> None:
    X, y = _synthetic_dataset(700, informative=True)
    r = train(X, y, FEATURE_NAMES, horizon_bars=5, horizon_s=5)
    assert r is not None
    oos = r.oos
    assert oos["accuracy"] > 0.6 and oos["edge_vs_prior"] > 0.15
    assert r.calibration in ("isotonic", "sigmoid")
    assert set(r.class_prior) == {"down", "flat", "up"}
    assert FEATURE_NAMES[0] in r.importance  # the informative feature ranks
    p = r.model.predict_proba(X[:5])
    assert p.shape == (5, 3) and np.allclose(p.sum(axis=1), 1.0)

    Xn, yn = _synthetic_dataset(700, informative=False)
    rn = train(Xn, yn, FEATURE_NAMES, horizon_bars=5, horizon_s=5)
    assert rn is not None
    # TimeSeriesSplit(gap) + honest metrics: no edge to be found on shuffled labels
    assert rn.oos["edge_vs_prior"] < 0.05 and rn.oos["accuracy"] < 0.45  # no edge claimed


def test_training_declines_single_class_or_tiny_sets() -> None:
    X = np.zeros((50, N_FEATURES))
    assert train(X, np.zeros(50, dtype=int), FEATURE_NAMES, 5, 5) is None
    assert train(X[:10], np.array([0, 1, 2] * 3 + [1]), FEATURE_NAMES, 5, 5) is None


# ── Drift ─────────────────────────────────────────────────────────


def test_drift_monitor_statuses() -> None:
    d = DriftMonitor(window=100, min_n=10)
    assert d.summary()["status"] == "no_data"
    d.reset_baseline(
        {"down": 0.3, "flat": 0.4, "up": 0.3}, oos_log_loss=0.9, oos_prior_log_loss=1.09
    )
    for i in range(30):  # confident and right → edge
        d.record(Outcome(i, (0.1, 0.1, 0.8), 2, 2, 3.0))
    s = d.summary()
    assert s["status"] == "edge" and s["hit_rate"] == 1.0 and s["edge_vs_prior"] > 0
    d2 = DriftMonitor(window=100, min_n=10)
    d2.reset_baseline({"down": 0.3, "flat": 0.4, "up": 0.3}, 0.9, 1.09)
    for i in range(30):  # confident and wrong → no edge
        d2.record(Outcome(i, (0.1, 0.1, 0.8), 2, 0, -3.0))
    assert d2.summary()["status"] == "no_edge"
    assert len(d2.series(5)) == 5 and d2.series(1)[0]["hit"] is False


def test_drift_hit_rate_comes_with_the_priors_own_hit_rate() -> None:
    # A model that calls "flat" every time is right as often as flat occurs, which is exactly
    # what calling the prior's majority class scores: a high hit rate alone is no skill.
    d = DriftMonitor(window=100, min_n=10)
    d.reset_baseline({"down": 0.1, "flat": 0.8, "up": 0.1}, 0.6, 0.65)
    for i in range(50):
        d.record(Outcome(i, (0.1, 0.8, 0.1), 1, 2 if i % 5 == 0 else 1, 0.0))  # 80 % flat
    s = d.summary()
    assert s["hit_rate"] == s["prior_hit_rate"] == 0.8


# ── Backtest ──────────────────────────────────────────────────────


def test_strategy_spec_validation_and_examples() -> None:
    for k, v in EXAMPLE_SPECS.items():
        spec = StrategySpec.model_validate(v)
        assert spec.describe()["entry_long"], k
    assert StrategySpec.model_validate(EXAMPLE_SPECS["model_signal"]).uses_model
    with pytest.raises(ValidationError):
        StrategySpec.model_validate({"side": "long"})  # no entry
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(
            {"side": "long", "entry_long": {"f": "ofi_z", "op": ">", "v": 1}}
        )  # no exit


def _walk(n: int, step_bps: float) -> list[Bar]:
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + step_bps / 10_000))
    return [_bar(i, c, ofi_z=(2.0 if i % 40 == 0 else 0.0)) for i, c in enumerate(closes)]


def test_backtest_accounting_matches_hand_computation() -> None:
    # Enter long whenever ofi_z > 1 (every 40 bars), exit after 10 bars; price drifts +1 bps/bar.
    spec = StrategySpec.model_validate(
        {"side": "long", "size_pct": 100, "entry_long": {"f": "ofi_z", "op": ">", "v": 1.0},
         "exit": {"f": "bars_held", "op": ">=", "v": 10}}
    )  # fmt: skip
    bars = _walk(200, 1.0)
    out = run_backtest(bars, spec, initial_capital=10_000, commission_bps=1.0, slippage_bps=0.5)
    m = out.metrics
    assert m["total_trades"] == 5 and all(t["reason"] == "exit_rule" for t in out.trades)
    # signal on bar i → filled at bar i+1 close; exit decided at bars_held ≥ 10 → filled next bar
    t0 = out.trades[0]
    assert t0["entry_ts"] == bars[1].ts_ms and t0["exit_ts"] == bars[12].ts_ms
    fee, slip = 1e-4, 0.5e-4
    entry = bars[1].close * (1 + slip)
    exit_ = bars[12].close * (1 - slip)
    qty = 10_000 / entry
    expected_pnl = (exit_ - entry) * qty - (entry + exit_) * qty * fee
    assert math.isclose(t0["pnl"], expected_pnl, rel_tol=1e-6)
    assert math.isclose(m["total_pnl"], sum(t["pnl"] for t in out.trades), abs_tol=1e-3)
    assert math.isclose(m["final_capital"], 10_000 + m["total_pnl"], abs_tol=1e-3)
    assert m["win_rate"] == 1.0 and m["exposure_pct"] > 0 and len(out.equity_curve) == 200
    assert out.equity_curve[-1][1] == m["final_capital"]


def test_backtest_stop_loss_take_profit_and_short() -> None:
    bars = _walk(120, -2.0)  # falling market
    spec = StrategySpec.model_validate(
        {"side": "short", "entry_short": {"f": "ofi_z", "op": ">", "v": 1.0},
         "take_profit_bps": 10, "stop_loss_bps": 5}
    )  # fmt: skip
    out = run_backtest(bars, spec, initial_capital=1_000, commission_bps=0, slippage_bps=0)
    assert out.metrics["total_trades"] >= 1
    assert all(t["side"] == "short" and t["reason"] == "take_profit" for t in out.trades)
    assert all(math.isclose(t["pnl_bps"], 10.0, abs_tol=1e-6) for t in out.trades)
    rising = _walk(120, 2.0)
    out2 = run_backtest(rising, spec, initial_capital=1_000, commission_bps=0, slippage_bps=0)
    assert all(
        t["reason"] == "stop_loss" and math.isclose(t["pnl_bps"], -5.0, abs_tol=1e-6)
        for t in out2.trades
    )


def test_backtest_never_stops_out_on_the_fill_bar() -> None:
    # Signal on bar 0 → filled at bar 1's close (100.00). Bar 1's low (99.70) printed
    # *before* the fill, and price never trades below 100 afterwards.
    spec = StrategySpec.model_validate(
        {"side": "long", "size_pct": 100, "entry_long": {"f": "ofi_z", "op": ">", "v": 1.5},
         "stop_loss_bps": 20, "max_hold_s": 5}
    )  # fmt: skip
    bars = [_bar(i, 100.0, ofi_z=2.0 if i == 0 else 0.0) for i in range(10)]
    bars[1].low = 99.70
    out = run_backtest(bars, spec, commission_bps=0, slippage_bps=0)
    assert [t["reason"] for t in out.trades] == ["max_hold"]
    assert out.trades[0]["pnl"] == 0.0


def test_backtest_uses_model_probabilities_when_provided() -> None:
    bars = _walk(100, 1.0)
    spec = StrategySpec.model_validate(EXAMPLE_SPECS["model_signal"])
    probs = {
        b.ts_ms: {"p_up": 0.7 if i % 30 == 0 else 0.2, "p_down": 0.1} for i, b in enumerate(bars)
    }
    out = run_backtest(bars, spec, probs_by_ts=probs)
    assert out.metrics["total_trades"] >= 2 and all(t["side"] == "long" for t in out.trades)
    none = run_backtest(bars, spec)  # no probabilities → p_up missing → never enters
    assert none.metrics["total_trades"] == 0


async def test_synthetic_history_returns_every_requested_bar() -> None:
    # The generator used to hand back the engine's 600-bar chart ring, so the default
    # request for 3,600 bars quietly backtested on 600. Ask for more than the ring holds.
    bars = await asyncio.to_thread(generate_synthetic_bars, S, 700)
    assert len(bars) == 700
    assert all(b.ts_ms - a.ts_ms == 1000 for a, b in pairwise(bars))


@pytest.mark.parametrize(
    "template",
    ["{value.__class__}", "{value[0]}", "{value!r}", "{value:>50000000}", "{nope}", "{value:{x}}"],
)
def test_alert_templates_reject_attribute_access_conversions_and_huge_widths(template: str) -> None:
    assert template_error(template) is not None
    assert render(template, "default", value=1.5) == "default"


def test_alert_templates_render_whitelisted_fields() -> None:
    t = "{symbol} {field} = {value:+.2f} (limit {threshold:,.0f})"
    assert template_error(t) is None
    msg = render(t, "d", value=2.345, threshold=12_000, field="spread_z", symbol="BTCUSDT")
    assert msg == "BTCUSDT spread_z = +2.35 (limit 12,000)"
    assert render("{value:.2f}", "fallback", value="trending") == "fallback"  # never raises


def test_metrics_helpers() -> None:
    assert max_drawdown_pct([100, 120, 90, 130]) == pytest.approx(25.0)
    sharpe, sortino = sharpe_sortino(np.array([100.0, 101.0, 102.0, 103.0]))
    assert sharpe > 0 and sortino == 0.0  # no downside moves
