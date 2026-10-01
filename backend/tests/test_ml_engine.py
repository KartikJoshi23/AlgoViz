"""ML engine integration — training on a live synthetic stream, persistence, restart rebuild."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from algoviz.config import Settings
from algoviz.db import async_session, init_db
from algoviz.market.service import SymbolEngine
from algoviz.market.synthetic import SyntheticSource
from algoviz.ml.engine import MLEngine
from algoviz.ws.hub import Hub

S = "BTCUSDT"


def _cfg(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        ML_MIN_DATA_POINTS=150,
        ML_RETRAIN_EVERY_SAMPLES=100_000,
        ML_MODEL_DIR=tmp_path / "models",
        DRIFT_MIN_N=20,
        ZSCORE_WARMUP_S=30,
    )


async def _run_until(engine: SymbolEngine, predicate, timeout_s: float) -> None:  # type: ignore[no-untyped-def]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not met in time")


@pytest.mark.slow
async def test_engine_trains_predicts_and_resolves_on_synthetic_stream(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    await init_db()  # registry rows need the schema even when the app fixture hasn't run
    src = SyntheticSource(S, seed=21, speed=0, start_ms=1_700_000_000_000)
    engine = SymbolEngine(S, cfg, src, Hub(), writer=None, preload=False)
    assert engine.ml is not None and engine.signals is not None
    await engine.start()
    try:
        await _run_until(engine, lambda: engine.ml.ready, timeout_s=120)  # type: ignore[union-attr]
        info = engine.ml.model_info()
        assert info["status"] == "ready" and info["model_version"] == 1
        assert info["training_samples"] >= cfg.ML_MIN_DATA_POINTS
        assert info["metrics"]["oos"] and "edge_vs_prior" in info["metrics"]["oos"]
        assert set(info["class_prior"]) == {"down", "flat", "up"}
        assert (tmp_path / "models" / S / "v1.joblib").exists()

        # live predictions flow and resolve into the drift monitor
        await _run_until(engine, lambda: engine.ml.drift.total_resolved >= 25, timeout_s=60)  # type: ignore[union-attr]
        p = engine.ml.last_payload()
        assert p and p["status"] == "ready" and p["signal"] in ("long", "short", "flat")
        # payload probabilities are rounded to 4 dp, so allow the rounding slack
        assert p["p_up"] is not None and abs(p["p_up"] + p["p_down"] + p["p_flat"] - 1) < 2e-4
        drift = engine.ml.drift.summary()
        assert drift["status"] in ("edge", "no_edge", "decayed") and drift["n"] >= 20
        shap = await engine.ml.explain()
        assert (
            shap
            and len(shap["contributions"]) == 10
            and shap["predicted_class"] in ("up", "down", "flat")
        )
        # features carry the model probabilities so signal rules can use them
        snap = engine.features.snapshot(engine.now_ms())
        assert snap.p_up is not None
        assert engine.signals.evaluations > 100
    finally:
        await engine.stop()

    # ── restart: the registry restores the model and history rebuilds the training set
    bars = list(engine.bar_ring)
    ml2 = MLEngine(S, cfg, async_session, persist=False)
    await ml2.start(history=bars)
    assert ml2.ready and ml2.version == 1
    assert ml2.model_info()["samples_available"] > 100  # rebuilt from bars, not zero
    await ml2.stop()
