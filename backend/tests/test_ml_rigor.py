"""Stage H — the model is evaluated as served, and every claim the UI makes about it holds."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sklearn.ensemble import HistGradientBoostingClassifier

from alembic import command
from algoviz.backtest.engine import bar_context, run_backtest
from algoviz.backtest.service import generate_synthetic_bars
from algoviz.backtest.strategy import StrategySpec
from algoviz.config import Settings
from algoviz.core.time import utcnow
from algoviz.db import _alembic_config, async_session
from algoviz.market.bars import Bar
from algoviz.market.persistence import read_bar_exports, write_bar_export
from algoviz.market.regime import RegimeDetector, TrendTracker, hac_t_stat
from algoviz.ml.engine import MLEngine
from algoviz.ml.evaluation import brier_decomposition, pool_curves, reliability_curve
from algoviz.ml.explain import Explainer
from algoviz.ml.features import (
    FEATURE_NAMES,
    LOOKBACK,
    N_FEATURES,
    QuantityScales,
    RollingMedian,
    feature_vector,
)
from algoviz.ml.registry import ModelRegistry, model_manifest
from algoviz.ml.study import (
    ABLATE_TOP,
    ABLATIONS,
    ALL_FEATURES,
    MIN_FOLDS_BEATING,
    ConfigResult,
    LabelSpec,
    build_samples,
    decide,
    render,
    run_study,
)
from algoviz.ml.train import (
    ES_TAIL,
    FoldMetrics,
    TailStoppedHGB,
    TrainResult,
    base_estimators,
    fit_model,
    score_split,
    trailing_prior_proba,
    train,
    walk_forward,
)

S = "BTCUSDT"

pytestmark = pytest.mark.usefixtures("capped_threads")


@pytest.fixture(scope="module")
def trained() -> tuple[TrainResult, np.ndarray]:
    X, y = _dataset(3000)
    r = train(X, y, FEATURE_NAMES, horizon_bars=5, horizon_s=5)
    assert r is not None
    return r, X


def _dataset(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(seed)
    X = rng.normal(size=(n, N_FEATURES))
    score = 1.2 * X[:, 0] - 0.8 * X[:, 5] + rng.normal(scale=0.7, size=n)
    y = np.where(score > 0.8, 2, np.where(score < -0.8, 0, 1))
    return X, y


# ── Scores ────────────────────────────────────────────────────────


def test_brier_decomposition_is_exact_for_forecasts_constant_within_bins() -> None:
    rng = np.random.RandomState(1)
    n = 3000
    # forecasts on bin centres (0.05, 0.15, …) so the within-bin term vanishes
    raw = rng.choice(np.arange(10) / 10 + 0.05, size=(n, 3))
    proba = raw / raw.sum(axis=1, keepdims=True)
    proba = np.round(proba * 10 - 0.5) / 10 + 0.05  # re-snap after normalising
    y = rng.randint(0, 3, size=n)
    d = brier_decomposition(proba, y)
    assert math.isclose(
        d["brier"], d["reliability"] - d["resolution"] + d["uncertainty"], abs_tol=1e-9
    )
    assert d["reliability"] >= 0 and d["resolution"] >= 0 and 0 < d["uncertainty"] <= 2 / 3


def test_reliability_curves_pool_exactly() -> None:
    rng = np.random.RandomState(2)
    p = rng.dirichlet([1, 1, 1], size=900)
    y = rng.randint(0, 3, size=900)
    whole = reliability_curve(p, y)
    pooled = pool_curves([reliability_curve(p[:400], y[:400]), reliability_curve(p[400:], y[400:])])
    for name in whole:
        for a, b in zip(whole[name], pooled[name], strict=True):
            assert a[0] == b[0] and math.isclose(a[1], b[1], abs_tol=2e-5)
            assert math.isclose(a[2], b[2], abs_tol=2e-5)


# ── The served recipe ─────────────────────────────────────────────


def test_early_stopping_validates_on_the_time_ordered_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    original = HistGradientBoostingClassifier.fit

    def spy(self: Any, X: Any, y: Any, sample_weight: Any = None, **kw: Any) -> Any:
        seen["fit_rows"] = X[:, 0].copy()
        seen["val_rows"] = kw["X_val"][:, 0].copy()
        return original(self, X, y, sample_weight, **kw)

    monkeypatch.setattr(HistGradientBoostingClassifier, "fit", spy)
    X, y = _dataset(1000)
    X[:, 0] = np.arange(1000)  # the row index, so the split can be read back
    TailStoppedHGB(gap=5).fit(X, y)
    n_val = int(1000 * ES_TAIL)
    assert seen["val_rows"].min() == 1000 - n_val and seen["val_rows"].max() == 999
    # every fit row precedes the tail by at least the embargo: no interleaving, no overlap
    assert seen["fit_rows"].max() == 1000 - n_val - 5 - 1


def test_calibration_survives_a_class_missing_from_its_split_models() -> None:
    # "up" occurs only in the last calibration fold, so every split model is fitted on two
    # classes. scikit-learn used to calibrate each one's p(flat) as "down" and fill only that
    # column: the served ensemble said p(down) = 1 for every row.
    rng = np.random.RandomState(0)
    X = rng.normal(size=(900, 4))
    y = np.where(rng.rand(900) < 0.03, 0, 1)
    y[-100::20] = 2
    model, method = fit_model(X, y, gap=5)
    assert method == "sigmoid" and list(model.classes_) == [0, 1, 2]
    p = model.predict_proba(X)
    assert abs(p[:, 1].mean() - (y == 1).mean()) < 0.05
    assert p[:, 0].mean() < 0.1 and p[:, 2].mean() < 0.05


def test_folds_are_scored_calibrated_with_reliability_and_brier_terms(
    trained: tuple[TrainResult, np.ndarray],
) -> None:
    r, _ = trained
    assert len(r.folds) == 4
    assert {f.calibration for f in r.folds} <= {"isotonic", "sigmoid", "none"}
    assert r.folds[-1].calibration == "isotonic" and r.calibration == "isotonic"
    oos = r.oos
    assert oos["log_loss"] < oos["prior_log_loss"] and oos["edge_vs_prior"] > 0.1
    for f in r.folds:
        assert math.isclose(
            f.brier, f.brier_reliability - f.brier_resolution + f.brier_uncertainty, abs_tol=0.02
        )
        assert sum(n for n, _, _ in f.reliability["up"]) == f.n_test
    assert 0 <= oos["calibration_error"] < 0.1
    payload = r.metrics_payload()
    assert set(payload["reliability"]) == {"down", "flat", "up"}
    assert all(b["n"] > 0 for b in payload["reliability"]["up"])  # empty bins left out
    # the served model is the same recipe: a calibrated ensemble over the calibration splits
    assert len(r.base_models) == len(base_estimators(r.model)) == 3


def test_importance_is_held_out_log_loss_and_finds_the_signal(
    trained: tuple[TrainResult, np.ndarray],
) -> None:
    r, _ = trained
    top = list(r.importance)[:2]
    assert set(top) == {FEATURE_NAMES[0], FEATURE_NAMES[5]}, r.importance
    assert r.importance[FEATURE_NAMES[0]] > 0.05  # nats of held-out log-loss
    noise = [v for k, v in r.importance.items() if k not in top]
    assert all(v < 0.02 for v in noise)
    assert set(r.importance_std) == set(r.importance)


def test_logistic_baseline_is_regularised_against_heavy_tails() -> None:
    X, y = _dataset(2000)
    rng = np.random.RandomState(3)
    X[:, 37] = rng.standard_t(1.5, size=2000) * 50  # a kurtosis-like feature with outliers
    r = train(X, y, FEATURE_NAMES, horizon_bars=5, horizon_s=5)
    assert r is not None
    assert all(f.logistic_log_loss < f.prior_log_loss for f in r.folds)


def test_shap_explains_the_served_ensembles_mean_raw_log_odds(
    trained: tuple[TrainResult, np.ndarray],
) -> None:
    r, X = trained
    ex = Explainer(r.model, r.base_models, FEATURE_NAMES)
    for i in range(ex.size):
        ex.warm(i)
    out = ex.explain(X[-1], top=N_FEATURES)
    assert out is not None and out["models_averaged"] == len(r.base_models)
    cls = ["down", "flat", "up"].index(out["predicted_class"])
    served = r.model.predict_proba(X[-1:])[0]
    assert out["predicted_class"] == ["down", "flat", "up"][int(np.argmax(served))]
    assert math.isclose(out["probability"], float(served.max()), abs_tol=1e-4)
    margins = [m.decision_function(X[-1:])[0, list(m.classes_).index(cls)] for m in r.base_models]
    assert math.isclose(out["prediction_logit"], float(np.mean(margins)), abs_tol=1e-3)
    assert math.isclose(
        out["base_value"] + sum(c["shap"] for c in out["contributions"]),
        out["prediction_logit"],
        abs_tol=1e-3,
    )


# ── Registry manifest ─────────────────────────────────────────────


def _result(manifest: dict[str, Any]) -> TrainResult:
    X, y = _dataset(600)
    r = train(X, y, FEATURE_NAMES, horizon_bars=5, horizon_s=5)
    assert r is not None
    r.manifest = manifest
    return r


def test_registry_refuses_a_model_trained_for_another_configuration(tmp_path: Path) -> None:
    reg = ModelRegistry(tmp_path, S)
    current = model_manifest(5, 5, 1.0, 0.5)
    reg.save(_result(current), 3)
    version, loaded = reg.load_latest(current)
    assert version == 3 and loaded is not None and loaded.manifest == current
    assert loaded.folds[0].reliability  # fold curves survive the round trip

    other_horizon = model_manifest(10, 10, 1.0, 0.5)
    assert reg.load_latest(other_horizon) == (3, None)  # refused, but the number is kept
    old_schema = current | {"feature_schema": "0123456789abcdef"}
    assert reg.load_latest(old_schema) == (3, None)
    assert reg.load_latest(current | {"lookback_bars": LOOKBACK + 1})[1] is None


# ── Scale-free quantities ─────────────────────────────────────────


def test_rolling_median_matches_brute_force() -> None:
    rng = np.random.RandomState(4)
    rm = RollingMedian(window=50)
    values: list[float] = []
    for _ in range(400):
        v = float(rng.choice([0.0, rng.exponential(3.0)]))
        rm.push(v)
        values.append(v)
        window = [x for x in values[-50:] if x > 0]
        expected = float(np.median(window)) if window else None
        assert rm.value == expected


def _flow_bar(i: int, scale: float, rng: np.random.RandomState) -> Bar:
    b = Bar(S, i * 1000, "t", 100, 100, 100, 100 + 0.01 * math.sin(i), None, 0, 0, 0)
    vol = float(rng.exponential(2.0))
    b.volume, b.buy_volume = vol * scale, vol * scale * 0.6
    b.trade_count = int(rng.poisson(5))
    b.velocity = float(b.trade_count)
    b.ofi = float(rng.normal()) * scale
    b.liquidity_5bps, b.liquidity_10bps = 20 * scale, 40 * scale
    b.book_slope = 4 * scale
    b.spread_bps = 0.01
    b.extra = {"ofi_5s": float(rng.normal()) * scale, "ofi_30s": float(rng.normal()) * scale}
    return b


def test_quantity_features_are_invariant_to_the_symbols_size_unit() -> None:
    vectors = []
    for scale in (1.0, 1_000.0):  # e.g. BTC vs a coin priced 1000× lower
        rng = np.random.RandomState(5)
        scales = QuantityScales()
        bars = []
        for i in range(300):
            bar = _flow_bar(i, scale, rng)
            scales.push(bar)
            bars.append(bar)
        v = feature_vector(bars, scales.current())
        assert v is not None
        vectors.append(v)
    assert np.allclose(vectors[0], vectors[1], rtol=1e-9, atol=1e-9)


# ── Trend ─────────────────────────────────────────────────────────


def test_hac_t_stat_flags_drift_and_discounts_autocorrelated_noise() -> None:
    rng = np.random.RandomState(6)
    drift = 0.3 + rng.normal(size=120)
    assert hac_t_stat(drift) > 2
    # bid–ask bounce: strongly negatively autocorrelated, zero drift
    bounce = np.tile([1.0, -1.0], 60) + rng.normal(scale=0.1, size=120)
    assert abs(hac_t_stat(bounce)) < 2
    # positively autocorrelated noise: a plain t-test would call this a trend
    e = rng.normal(size=120)
    ar = np.zeros(120)
    for i in range(1, 120):
        ar[i] = 0.8 * ar[i - 1] + e[i]
    plain = ar.mean() / (ar.std(ddof=1) / math.sqrt(len(ar)))
    assert abs(hac_t_stat(ar)) < abs(plain)


def test_trend_enters_at_two_and_releases_below_one_and_a_half() -> None:
    tr = TrendTracker(window=60)
    rng = np.random.RandomState(7)
    for _ in range(60):
        tr.push(0.5 + rng.normal(scale=0.5))
    assert tr.label == "up" and tr.t >= 2
    while tr.t >= 1.5:  # drift fades: holds through the band between 1.5 and 2
        tr.push(rng.normal(scale=0.5))
        if 1.5 <= tr.t < 2:
            assert tr.label == "up"
    assert tr.label == "flat"


def test_detector_reports_trend_separately_and_resets_it_across_a_gap() -> None:
    rd = RegimeDetector(min_bars=1_000_000)
    rng = np.random.RandomState(8)
    price, ts = 100.0, 0
    for _ in range(130):
        price *= 1.0002 + rng.normal(scale=0.0003)
        ts += 1000
        st = rd.push_bar(Bar(S, ts, "t", price, price, price, price, None, 0, 0, 0))
    assert st.trend == "up" and st.trend_t > 2 and st.direction > 0.7
    assert st.label == "normal"  # vol_z 0: a steady climb is a trend, not a volatility state
    st = rd.push_bar(Bar(S, ts + 60_000, "t", price, price, price, price, None, 0, 0, 0))
    assert st.trend == "flat" and st.trend_t == 0.0


def test_backtests_can_condition_on_the_trend() -> None:
    bars = []
    price = 100.0
    for i in range(400):
        price *= 1.0003 if i >= 200 else 1.0 + (0.0003 if i % 2 else -0.0003)
        bars.append(Bar(S, i * 1000, "t", price, price, price, price, None, 1, 0.5, 1))
    spec = StrategySpec.model_validate(
        {
            "side": "long",
            "size_pct": 10,
            "entry_long": {"f": "trend", "op": "==", "v": "up"},
            "exit": {"f": "bars_held", "op": ">=", "v": 5},
        }
    )
    out = run_backtest(bars, spec)
    assert out.trades and min(t["entry_ts"] for t in out.trades) > 200_000  # only once it trends
    assert "trend" not in bar_context(bars[0])  # recomputed by the engine, not read from the bar


# ── Migration ─────────────────────────────────────────────────────


def test_regime_split_migration_rewrites_stored_labels_and_strategies(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db.as_posix()}")
    command.upgrade(cfg, "98b588110c0f")
    con = sqlite3.connect(db)
    now = utcnow().isoformat()
    for i, label in enumerate(("quiet", "trending", "volatile", "breakout", None)):
        con.execute(
            "insert into market_snapshots (symbol, timestamp, source, open, high, low, close,"
            " volume, buy_volume, trade_count, regime) values (?, ?, 't', 1, 1, 1, 1, 0, 0, 0, ?)",
            (S, f"2026-09-0{i + 1}T00:00:00", label),
        )
    con.execute(
        "insert into users (id, username, hashed_password, is_active, is_admin, created_at,"
        " updated_at) values (1, 'u', 'x', 1, 0, ?, ?)",
        (now, now),
    )
    config = {
        "side": "both",
        "entry_long": {"all": [{"f": "regime", "op": "in", "v": ["trending", "breakout"]}]},
        "exit": {"not": {"f": "regime", "op": "==", "v": "quiet"}},
    }
    con.execute(
        "insert into strategies (id, user_id, name, strategy_type, config, is_active, is_public,"
        " created_at, updated_at) values (1, 1, 's', 'rule_based', ?, 1, 0, ?, ?)",
        (json.dumps(config), now, now),
    )
    con.commit()
    con.close()

    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    labels = [r[0] for r in con.execute("select regime from market_snapshots order by timestamp")]
    assert labels == ["calm", "normal", "elevated", "extreme", None]
    stored = json.loads(con.execute("select config from strategies").fetchone()[0])
    assert stored["entry_long"]["all"][0]["v"] == ["normal", "extreme"]
    assert stored["exit"]["not"]["v"] == "calm"
    assert "trend" in [r[1] for r in con.execute("pragma table_info(market_snapshots)")]
    con.close()


# ── Edge study (Stage S) ──────────────────────────────────────────


def test_the_trailing_prior_knows_only_labels_resolved_by_each_prediction() -> None:
    y = np.array([0, 0, 2, 2, 2, 1])
    p = trailing_prior_proba(y, np.array([0, 3, 5]), horizon_bars=2, window=2)
    assert np.allclose(
        p,
        [
            [1 / 3, 1 / 3, 1 / 3],  # nothing has resolved two bars before row 0
            [3 / 5, 1 / 5, 1 / 5],  # rows 0–1 resolved: down, down
            [1 / 5, 1 / 5, 3 / 5],  # rows 0–3 resolved, the window keeps the last two: up, up
        ],
    )


def test_folds_score_the_trailing_prior_and_older_artefacts_still_load(
    trained: tuple[TrainResult, np.ndarray],
) -> None:
    r, _ = trained
    assert all(f.trailing_prior_log_loss is not None for f in r.folds)
    assert "edge_vs_trailing_prior" in r.oos
    saved = r.folds[0].as_dict()
    del saved["trailing_prior_log_loss"]  # an artefact trained before the baseline existed
    old = FoldMetrics.from_dict(saved)
    assert old.trailing_prior_log_loss is None
    assert "edge_vs_trailing_prior" not in dataclasses.replace(r, folds=[old]).oos


def test_the_rule_adopts_a_planted_edge_and_nothing_less() -> None:
    X, y = _dataset(3000)
    spec = LabelSpec(5, 1.0, 0.5)
    dev, test = np.arange(2250), np.arange(2255, 3000)

    folds, _ = walk_forward(X[dev], y[dev], 5)
    planted = ConfigResult(spec, ALL_FEATURES, len(y), float((y == 1).mean()), folds)
    held, _ = score_split(X, y, dev, test, 5)
    assert planted.beating == len(folds) >= MIN_FOLDS_BEATING
    assert decide(planted, held, days=8).adopt
    too_soon = decide(planted, held, days=1)  # the same result on a day of bars decides nothing
    assert not too_soon.adopt and too_soon.reason.startswith("preliminary")

    # Beating the trailing prior while losing to the class prior is no edge (E9): the
    # first rule tested the trailing prior alone and would have adopted this.
    def lose_to_the_class_prior(f: FoldMetrics) -> FoldMetrics:
        return dataclasses.replace(f, prior_log_loss=f.log_loss - 0.01)

    weaker = ConfigResult(
        spec, ALL_FEATURES, len(y), planted.flat_share, [lose_to_the_class_prior(f) for f in folds]
    )
    assert all(f.trailing_prior_log_loss > f.log_loss for f in weaker.folds)
    assert weaker.beating == 0
    verdict = decide(weaker, lose_to_the_class_prior(held), days=8)
    assert not verdict.adopt and verdict.reason.startswith("no edge")

    shuffled = np.random.RandomState(3).permutation(y)
    folds, _ = walk_forward(X[dev], shuffled[dev], 5)
    noise = ConfigResult(spec, ALL_FEATURES, len(y), float((shuffled == 1).mean()), folds)
    held, _ = score_split(X, shuffled, dev, test, 5)
    verdict = decide(noise, held, days=8)
    assert not verdict.adopt and verdict.reason.startswith("no edge")


@pytest.fixture(scope="module")
def synthetic_bars() -> list[Bar]:
    return generate_synthetic_bars(S, 1200)


async def test_the_study_labels_exactly_as_the_engine_does(
    tmp_path: Path, synthetic_bars: list[Bar]
) -> None:
    bars = [dataclasses.replace(b) for b in synthetic_bars]
    for b in bars[600:]:
        b.ts_ms += 60_000  # a gap: no label may reach across it
    cfg = Settings(_env_file=None, ML_MODEL_DIR=tmp_path)  # type: ignore[call-arg]
    samples = build_samples(bars, cfg)
    assert samples.sessions == 2

    ml = MLEngine(S, cfg, async_session, persist=False)
    for b in bars:
        ml.ingest_bar(b, live=False)
    _, y_engine, _ = ml.training_set()
    served = LabelSpec(cfg.ML_HORIZON_S, cfg.ML_BARRIER_K, cfg.ML_MIN_BARRIER_BPS)
    keep, y = samples.labels(served)
    assert keep.all() and np.array_equal(y, y_engine)
    longer, _ = samples.labels(LabelSpec(60, 1.0, 0.5))
    assert longer.sum() == keep.sum() - 2 * (60 - served.horizon_s)  # each session's last minute


async def test_the_study_scores_each_configuration_and_reports_without_deciding(
    tmp_path: Path, synthetic_bars: list[Bar]
) -> None:
    cfg = Settings(_env_file=None, ML_MODEL_DIR=tmp_path)  # type: ignore[call-arg]
    specs = [LabelSpec(5, 1.0, 0.5), LabelSpec(30, 1.0, 1.0)]
    report = await asyncio.to_thread(run_study, synthetic_bars, cfg, specs=specs)

    scored = [r for r in report.results if r.folds]
    ablated = min(ABLATE_TOP, sum(r.ablation == ALL_FEATURES for r in scored))
    assert ablated == len(specs)  # both label definitions are scored, so both are ablated
    assert len(report.results) == len(specs) + ablated * (len(ABLATIONS) - 1)
    assert report.best is not None and report.best.mean_edge == max(r.mean_edge for r in scored)
    assert report.holdout is not None and report.holdout.trailing_prior_log_loss is not None
    assert not report.verdict.adopt and report.verdict.reason.startswith("preliminary")
    text = render(report)
    assert text.count("\n| ") == len(report.results) + 1  # the header and a row each
    assert "UTC" in text and "Holdout (" in text


def test_bar_exports_round_trip_and_overlap_without_duplicates(tmp_path: Path) -> None:
    bars = [
        Bar(S, 1_700_000_000_000 + i * 1000, "live", 100.0, 100.1, 99.9, 100.0 + i, 100.0, 2.0,
            1.0, 7, volatility_bps=2.5, regime="calm", extra={"ofi_5s": 0.25})
        for i in range(10)
    ]  # fmt: skip
    write_bar_export(bars[:6], tmp_path / "a.ndjson.gz")
    write_bar_export(bars[4:], tmp_path / "b.ndjson.gz")
    assert read_bar_exports([tmp_path / "b.ndjson.gz", tmp_path / "a.ndjson.gz"]) == bars
