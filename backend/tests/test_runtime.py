"""
Runtime isolation and data continuity — one regression test per Stage G finding.

The event loop carries the market feed, so every test here is about what must
*not* happen on it (blocking inference, duplicate training, CPU-bound scans per
diff) or about history that must not be spliced across an outage.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sqlalchemy import func, select

from algoviz.config import Settings
from algoviz.core.looplag import LoopLagMonitor
from algoviz.core.time import from_ms, utcnow
from algoviz.core.workers import InferenceWorker, WorkerError, WorkerTimeout, run_isolated
from algoviz.db import async_session, init_db
from algoviz.market.bars import SESSION_GAP_MS, Bar, trailing_segment
from algoviz.market.book import LocalOrderBook
from algoviz.market.events import DepthDiffEvent, DepthSnapshotEvent, SourceStatusEvent
from algoviz.market.features import StreamingFeatureEngine
from algoviz.market.persistence import BarWriter
from algoviz.market.regime import RegimeDetector
from algoviz.market.service import SymbolEngine
from algoviz.market.synthetic import SyntheticSource
from algoviz.ml.engine import InferenceJob, MLEngine, PredictionStore, _LivePrediction
from algoviz.ml.features import FEATURE_NAMES, LOOKBACK, N_FEATURES
from algoviz.ml.train import TrainResult
from algoviz.models import AlertHistory, AlertRule, MarketSnapshot, Prediction, User
from algoviz.ws.hub import Hub

S = "BTCUSDT"
T0 = 1_700_000_000_000


def _cfg(tmp_path: Path, **kw: Any) -> Settings:
    return Settings(_env_file=None, ML_MODEL_DIR=tmp_path / "models", **kw)  # type: ignore[call-arg]


def _walk(n: int, start_ms: int = T0, seed: int = 0, close0: float = 100.0) -> list[Bar]:
    rng = np.random.default_rng(seed)
    closes = close0 * np.exp(np.cumsum(rng.normal(0, 3e-4, n)))
    return [
        Bar(S, start_ms + i * 1000, "t", c, c * 1.0002, c * 0.9998, c, c, 1.0, 0.5, 5,
            volatility_bps=2.0)
        for i, c in enumerate(closes)
    ]  # fmt: skip


async def _max_loop_lag(awaitable: Awaitable[Any], tick_s: float = 0.01) -> tuple[Any, float]:
    """Await `awaitable` while a ticker measures how late the loop wakes it (seconds)."""
    worst = 0.0
    done = asyncio.Event()

    async def ticker() -> None:
        nonlocal worst
        loop = asyncio.get_running_loop()
        while not done.is_set():
            t0 = loop.time()
            await asyncio.sleep(tick_s)
            worst = max(worst, loop.time() - t0 - tick_s)

    task = asyncio.create_task(ticker())
    try:
        result = await awaitable
    finally:
        done.set()
        await task
    return result, worst


class _SlowModel:
    """Stands in for the calibrated ensemble: a predict that holds a thread for a while."""

    classes_ = np.array([0, 1, 2])

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        time.sleep(self.seconds)
        return np.tile([0.2, 0.5, 0.3], (len(X), 1))


def _stub_result(model: Any) -> TrainResult:
    return TrainResult(
        model=model,
        base_models=[model],
        feature_names=FEATURE_NAMES,
        n_samples=100,
        horizon_s=5,
        trained_at=utcnow(),
        folds=[],
        importance={},
        importance_std={},
        class_prior={"down": 0.2, "flat": 0.5, "up": 0.3},
        calibration="none",
    )


# ── Workers ───────────────────────────────────────────────────────


async def test_run_isolated_returns_raises_and_times_out() -> None:
    assert await run_isolated(pow, 2, 10, timeout_s=60) == 1024
    with pytest.raises(WorkerError, match="ValueError"):
        await run_isolated(int, "not a number", timeout_s=60)
    t0 = time.monotonic()
    with pytest.raises(WorkerTimeout):
        await run_isolated(time.sleep, 60, timeout_s=4)
    assert time.monotonic() - t0 < 30  # the sleeping child was terminated, not waited for


@pytest.mark.skipif(not hasattr(os, "nice"), reason="scheduling priority is POSIX-only")
async def test_isolated_work_yields_the_cpu_to_the_server() -> None:
    # os.nice(0) reports the caller's niceness: the child runs 10 steps below the server
    assert await run_isolated(os.nice, 0, timeout_s=60) == os.nice(0) + 10


async def test_inference_worker_runs_single_threaded_openmp() -> None:
    from threadpoolctl import threadpool_info

    def openmp_threads() -> list[int]:
        return [i["num_threads"] for i in threadpool_info() if i["user_api"] == "openmp"]

    w = InferenceWorker("t")
    try:
        inside = await w.run(openmp_threads)
    finally:
        w.shutdown()
    assert inside and set(inside) == {1}  # no parallel region, so no barrier to stall on


# ── ML engine ─────────────────────────────────────────────────────


async def test_prediction_runs_off_the_event_loop(tmp_path: Path) -> None:
    ml = MLEngine(S, _cfg(tmp_path), async_session, persist=False)
    ml._bundle = _stub_result(_SlowModel(0.4))
    job = InferenceJob(0, T0, 100.0, 1.0, np.zeros(N_FEATURES))
    try:
        payload, worst_lag = await _max_loop_lag(ml.predict(job))
    finally:
        ml._infer.shutdown()
    assert payload is not None and payload["status"] == "ready" and payload["p_up"] == 0.3
    # On the loop, this predict would stall it for its full 400 ms. The bound leaves room for
    # the session's synthetic engine sharing this loop (slowed further by coverage tracing in CI).
    assert worst_lag < 0.25, f"loop stalled {worst_lag * 1000:.0f} ms during a 400 ms predict"


async def test_training_is_single_flight_through_save_and_install(tmp_path: Path) -> None:
    await init_db()
    calls = 0
    release = asyncio.Event()

    async def offload(_fn: Any, *_args: Any) -> TrainResult:
        nonlocal calls
        calls += 1
        await release.wait()
        return _stub_result(_SlowModel(0.0))

    cfg = _cfg(
        tmp_path, ML_MIN_DATA_POINTS=50, ML_RETRAIN_EVERY_SAMPLES=1, ML_RETRAIN_MIN_INTERVAL_S=0
    )
    ml = MLEngine(S, cfg, async_session, persist=False, offload=offload)
    real_save = ml.registry.save

    def slow_save(result: TrainResult, version: int) -> Path:
        time.sleep(0.3)  # the window in which the old code started a second run
        return real_save(result, version)

    ml.registry.save = slow_save  # type: ignore[method-assign]
    await ml.start(history=_walk(200))
    await asyncio.sleep(0)  # let the training task reach the offload
    assert calls == 1 and ml.training
    for bar in _walk(20, start_ms=T0 + 200_000, seed=1):  # new samples arrive mid-training
        ml.ingest_bar(bar)
    release.set()
    while ml.training:
        ml.maybe_train()  # bars keep closing while the artefact is saved and installed
        await asyncio.sleep(0.01)
    assert calls == 1 and ml.version == 1
    await ml.stop()


async def test_a_restart_serves_the_stored_model_without_retraining(tmp_path: Path) -> None:
    await init_db()
    calls = 0

    async def offload(_fn: Any, *_args: Any) -> TrainResult:
        nonlocal calls
        calls += 1
        return _stub_result(_SlowModel(0.0))

    cfg = _cfg(tmp_path, ML_MIN_DATA_POINTS=50, ML_RETRAIN_EVERY_SAMPLES=100)
    first = MLEngine(S, cfg, async_session, persist=False, offload=offload)
    stored = _stub_result(_SlowModel(0.0))
    stored.n_samples = 150
    stored.manifest = first.manifest
    first.registry.save(stored, 1)
    first._infer.shutdown()

    ml = MLEngine(S, cfg, async_session, persist=False, offload=offload)
    await ml.start(history=_walk(240))  # ~170 labelled samples: past the old "retrain now" bar
    await asyncio.sleep(0)
    assert ml.ready and ml.version == 1 and not ml.training and calls == 0
    await ml.stop()


def test_ml_history_never_straddles_a_session_gap(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    ml = MLEngine(S, cfg, async_session, persist=False)
    first, second = _walk(300), _walk(300, start_ms=T0 + 3_600_000, seed=1, close0=120.0)
    for bar in first + second:
        ml.ingest_bar(bar, live=False)
    ml._infer.shutdown()
    assert ml.sessions == 2
    horizon_ms = cfg.ML_HORIZON_S * 1000
    lookback_ms = (LOOKBACK - 1) * 1000
    assert ml._sample_ts, "both sessions produce labelled samples"
    for ts in ml._sample_ts:
        if ts >= second[0].ts_ms:
            assert ts - lookback_ms >= second[0].ts_ms  # feature window inside session 2
        else:
            assert ts + horizon_ms <= first[-1].ts_ms  # label window inside session 1


# ── Engine: preload, staleness, regime continuity ─────────────────


@pytest.mark.parametrize(("age_s", "resumed"), [(3600, False), (10, True)])
async def test_preload_resumes_charts_only_from_a_fresh_trailing_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, age_s: int, resumed: bool
) -> None:
    now = T0 + 10_000_000
    last_end = now - age_s * 1000
    older = _walk(100, start_ms=last_end - 3_600_000)
    recent = _walk(100, start_ms=last_end - 99_000, seed=1)
    history = older + recent

    async def fake_load_bars(*_a: Any, **_kw: Any) -> list[Bar]:
        return list(reversed(history))  # newest_first, as the query returns them

    monkeypatch.setattr("algoviz.market.service.load_bars", fake_load_bars)
    src = SyntheticSource(S, seed=1, speed=1, start_ms=now)
    engine = SymbolEngine(S, _cfg(tmp_path), src, Hub(), writer=None, intelligence=False)
    returned = await engine._preload_bars()
    assert returned == history  # the model always gets the full history
    ring = list(engine.bar_ring)
    assert ring == (recent if resumed else [])  # charts never splice the older session in


async def test_paced_synthetic_event_time_keeps_up_with_the_wall_clock() -> None:
    src = SyntheticSource(S, seed=3, speed=20, start_ms=0)  # a 100 ms step every 5 ms
    task = asyncio.create_task(src.run(lambda _ev: None))
    t0 = time.perf_counter()
    await asyncio.sleep(1.0)
    elapsed = time.perf_counter() - t0
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    # a fixed sleep after each step ran ~20 % slow at speed 1 and ~3x slow here on Windows
    assert src.now_ms() / 1000 == pytest.approx(elapsed * 20, rel=0.1)


def test_trailing_segment_splits_at_gaps() -> None:
    a, b = _walk(5), _walk(5, start_ms=T0 + 5_000 + SESSION_GAP_MS + 1)
    assert trailing_segment(a + b) == b and trailing_segment(a) == a


def test_regime_returns_do_not_span_a_gap() -> None:
    det = RegimeDetector()
    bars = _walk(3)
    for bar in bars:
        det.push_bar(bar)
    jump = _walk(1, start_ms=T0 + 3_600_000, close0=bars[-1].close * 1.2)[0]  # +20 % an hour later
    det.push_bar(jump)
    assert det.training_matrix()[-1][0] == 0.0  # no 18 % "return" feeding the HMM


def test_feed_goes_stale_and_recovers(tmp_path: Path) -> None:
    hub = Hub()
    published: list[dict[str, Any]] = []
    hub.publish = lambda ch, _sym, data: published.append(data) if ch == "status" else None  # type: ignore[method-assign]
    engine = SymbolEngine(S, _cfg(tmp_path, FEED_STALE_S=10), SyntheticSource(S), hub, writer=None)
    engine._status = SourceStatusEvent(S, 0, "connected")
    engine._last_event_mono = 100.0
    engine._check_feed(105.0)
    assert not published
    engine._check_feed(111.0)
    assert published[-1]["status"] == "stale" and "no market data" in published[-1]["detail"]
    assert engine.stats()["status"] == "stale"
    engine._last_event_mono = 111.5  # data resumed
    engine._check_feed(112.0)
    assert published[-1]["status"] == "connected" and engine.stats()["status"] == "connected"
    assert engine.ml is not None
    engine.ml._infer.shutdown()


# ── Book: O(1) per diff, bounded size ─────────────────────────────


def _book() -> LocalOrderBook:
    b = LocalOrderBook(S)
    bids = [(100.0 - i * 0.01, 1.0) for i in range(50)] + [(96.0, 5.0)]  # a far level at −400 bps
    asks = [(100.01 + i * 0.01, 1.0) for i in range(50)] + [(104.0, 5.0)]
    b.apply_snapshot(DepthSnapshotEvent(S, T0, 10, bids, asks))
    return b


def test_book_metrics_scan_only_when_read() -> None:
    book = _book()
    fe = StreamingFeatureEngine(S, Settings(_env_file=None), "t")  # type: ignore[call-arg]
    for i in range(200):
        assert book.apply_diff(
            DepthDiffEvent(S, T0 + i, 11 + i, 11 + i, [(99.99, 1.0 + i % 3)], [])
        )
        fe.on_book(book, T0 + i)
    assert fe.book_scans == 0  # 200 diffs, zero O(levels) scans
    first = fe.snapshot(T0 + 200)
    fe.snapshot(T0 + 200)
    assert fe.book_scans == 1 and first.bid_qty == book._bids[-100.0]


def test_book_prune_drops_only_far_levels() -> None:
    book = _book()
    assert book.prune(250) == 2
    assert 96.0 not in [-k for k in book._bids] and 104.0 not in book._asks
    assert len(book) == 100 and book.best_bid == 100.0 and book.best_ask == 100.01


# ── Persistence ───────────────────────────────────────────────────


async def test_bar_writer_chunks_a_large_backlog() -> None:
    await init_db()
    writer = BarWriter(async_session, retention_days=7)
    start = int(time.time() * 1000) // 1000 * 1000 - 3_000_000_000  # a range no other test uses
    for bar in _walk(1_200, start_ms=start):  # ≈ 36 k parameters in one statement before
        writer.enqueue(bar)
    await writer.flush()
    assert writer.failed_flushes == 0 and writer.written == 1_200


async def test_retention_prunes_bars_predictions_and_alert_history() -> None:
    await init_db()
    old = utcnow().replace(year=2000)
    async with async_session() as s:
        user = (await s.execute(select(User).limit(1))).scalar_one_or_none()
        if user is None:
            user = User(username="retention-test", hashed_password="x")
            s.add(user)
            await s.flush()
        rule = AlertRule(user_id=user.id, name="r", symbol=S, condition_field="spread_z",
                         comparison="gt", threshold=1.0)  # fmt: skip
        s.add(rule)
        await s.flush()
        s.add(AlertHistory(rule_id=rule.id, rule_name="r", symbol=S, priority="low",
                           message="m", field="spread_z", triggered_at=old))  # fmt: skip
        s.add(Prediction(symbol=S, timestamp=old, horizon_s=5, mid_at_prediction=1.0,
                         p_down=0.3, p_flat=0.4, p_up=0.3, predicted_class="flat"))  # fmt: skip
        s.add(MarketSnapshot(symbol=S, timestamp=old, source="t", open=1, high=1, low=1,
                             close=1, volume=0, buy_volume=0, trade_count=0))  # fmt: skip
        await s.commit()
    deleted = await BarWriter(
        async_session, retention_days=7, prediction_retention_days=7, alert_retention_days=30
    ).prune()
    assert deleted["bars"] >= 1 and deleted["predictions"] >= 1 and deleted["alert_history"] >= 1
    async with async_session() as s:
        for model, col in (
            (Prediction, Prediction.timestamp),
            (AlertHistory, AlertHistory.triggered_at),
        ):
            n = (
                await s.execute(select(func.count()).select_from(model).where(col < from_ms(T0)))
            ).scalar_one()
            assert n == 0


async def test_prediction_store_requeues_after_a_failed_flush() -> None:
    await init_db()

    class _Broken:
        def __call__(self) -> Any:
            raise RuntimeError("database is locked")

    store = PredictionStore(_Broken(), S)  # type: ignore[arg-type]
    ts = int(time.time() * 1000) // 1000 * 1000 - 4_000_000_000
    lp = _LivePrediction(0, ts, 100.0, 1.0, (0.2, 0.5, 0.3), 1)
    store.add(lp, None, 5)
    store.resolve(lp, 2, 3.0)
    await store.flush()
    assert store.failed_flushes == 1 and store.backlog == 2  # nothing lost
    store._sf = async_session  # the database is back
    await store.flush()
    assert store.backlog == 0 and store.written == 1 and store.resolved == 1


# ── Loop lag ──────────────────────────────────────────────────────


def test_loop_lag_monitor_summarises_recent_lateness() -> None:
    m = LoopLagMonitor(interval_s=0.1, window=100)
    assert m.p99_ms() is None and m.stats()["samples"] == 0
    for late in [0.001] * 98 + [0.5, 0.002]:
        m.record(late)
    st = m.stats()
    assert st["samples"] == 100 and st["max_ms"] == 500.0 and st["p50_ms"] == 1.0
    assert m.p99_ms() is not None and m.p99_ms() > 1.0  # type: ignore[operator]
