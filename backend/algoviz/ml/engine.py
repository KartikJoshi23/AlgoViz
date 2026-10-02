"""
ML engine (per symbol)
======================

Consumes the 1 Hz bar stream:

- builds the feature vector for each bar (quantities over their rolling
  medians, measured up to that bar) and queues it for labelling;
- labels queued vectors once `horizon` more bars exist (triple barrier);
- predicts with the calibrated model on a dedicated inference thread,
  persists the prediction, and resolves it after the horizon into the drift
  monitor;
- trains in a spawned worker process (single-flight: the run, the artefact
  save and the swap are one task) and swaps the model in atomically;
  artefacts + registry rows survive restarts, and a stored model is served
  again only if its manifest (features, lookback, labels) matches;
- rebuilds its training set from persisted bars on startup so a restart does
  not reset the model to zero.

History is **session-aware**: a gap in the bar stream (outage, restart) resets
the rolling window, so no feature lookback and no label horizon ever spans
two sessions.

Only cheap bookkeeping runs on the event loop (`ingest_bar`); `predict`,
`explain` and training are awaited from elsewhere.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

import numpy as np
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algoviz.config import Settings
from algoviz.core.time import from_ms, utcnow
from algoviz.core.workers import InferenceWorker, Offload, run_isolated
from algoviz.market.bars import SESSION_GAP_MS, Bar
from algoviz.ml.drift import DriftMonitor, Outcome
from algoviz.ml.explain import Explainer
from algoviz.ml.features import FEATURE_NAMES, LOOKBACK, QuantityScales, feature_vector
from algoviz.ml.labels import CLASS_NAMES, barrier_bps, triple_barrier
from algoviz.ml.registry import ModelRegistry, model_manifest
from algoviz.ml.train import TrainResult, train
from algoviz.models import Prediction

logger = logging.getLogger("algoviz.ml")

BAR_BUFFER = 8_000
PRED_FLUSH_S = 5.0
MAX_PENDING_WRITES = 3_600  # an hour of predictions if the DB is unavailable


@dataclass(slots=True)
class _Pending:
    idx: int
    x: np.ndarray
    ts_ms: int
    close: float
    barrier: float


@dataclass(slots=True)
class InferenceJob:
    """What a closed bar needs predicted; built on the loop, predicted off it."""

    idx: int
    ts_ms: int
    close: float
    barrier: float
    x: np.ndarray


@dataclass(slots=True)
class _LivePrediction:
    idx: int
    ts_ms: int
    close: float
    barrier: float
    p: tuple[float, float, float]
    predicted: int


def _predict_proba(model: Any, x: np.ndarray) -> np.ndarray:
    """Class probabilities in the fixed [down, flat, up] order (runs on the inference thread)."""
    p = model.predict_proba(x.reshape(1, -1))[0]
    probs = np.full(3, 1e-6)
    for j, c in enumerate(model.classes_):
        probs[int(c)] = p[j]
    return probs / probs.sum()


class PredictionStore:
    """Batched persistence of predictions and their later resolution (re-queued on failure)."""

    def __init__(
        self, sf: async_sessionmaker[AsyncSession], symbol: str, enabled: bool = True
    ) -> None:
        self._sf = sf
        self._symbol = symbol
        self._enabled = enabled
        self._inserts: list[dict[str, Any]] = []
        self._updates: list[dict[str, Any]] = []
        self._task: asyncio.Task[None] | None = None
        self.written = 0
        self.resolved = 0
        self.failed_flushes = 0

    def add(self, lp: _LivePrediction, model_id: int | None, horizon_s: int) -> None:
        if not self._enabled:
            return
        self._inserts.append(
            {
                "symbol": self._symbol,
                "timestamp": from_ms(lp.ts_ms),
                "model_id": model_id,
                "horizon_s": horizon_s,
                "mid_at_prediction": lp.close,
                "p_down": lp.p[0],
                "p_flat": lp.p[1],
                "p_up": lp.p[2],
                "predicted_class": CLASS_NAMES[lp.predicted],
                "resolved": False,
            }
        )

    def resolve(self, lp: _LivePrediction, realised: int, realised_bps: float) -> None:
        if not self._enabled:
            return
        self._updates.append(
            {
                "sym": self._symbol,
                "ts": from_ms(lp.ts_ms),
                "realised_class": CLASS_NAMES[realised],
                "realised_move_bps": realised_bps,
                "resolved_at": utcnow(),
            }
        )

    @property
    def backlog(self) -> int:
        return len(self._inserts) + len(self._updates)

    async def start(self) -> None:
        if self._enabled and self._task is None:
            self._task = asyncio.create_task(self._loop(), name=f"pred-writer-{self._symbol}")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(PRED_FLUSH_S)
            await self.flush()

    async def flush(self) -> None:
        if not self._inserts and not self._updates:
            return
        inserts, self._inserts = self._inserts, []
        updates, self._updates = self._updates, []
        try:
            async with self._sf() as session:
                if inserts:
                    session.add_all(Prediction(**row) for row in inserts)
                for u in updates:
                    await session.execute(
                        update(Prediction)
                        .where(Prediction.symbol == u["sym"], Prediction.timestamp == u["ts"])
                        .values(
                            resolved=True,
                            realised_class=u["realised_class"],
                            realised_move_bps=u["realised_move_bps"],
                            resolved_at=u["resolved_at"],
                        )
                    )
                await session.commit()
            self.written += len(inserts)
            self.resolved += len(updates)
        except Exception:
            self.failed_flushes += 1
            logger.exception(
                "prediction flush failed (%d/%d rows re-queued)", len(inserts), len(updates)
            )
            # Same transaction ⇒ nothing was written: put everything back, oldest first.
            self._inserts = (inserts + self._inserts)[-MAX_PENDING_WRITES:]
            self._updates = (updates + self._updates)[-MAX_PENDING_WRITES:]


class MLEngine:
    def __init__(
        self,
        symbol: str,
        cfg: Settings,
        sf: async_sessionmaker[AsyncSession],
        *,
        persist: bool = True,
        offload: Offload | None = None,
    ) -> None:
        self.symbol = symbol.upper()
        self.cfg = cfg
        self._sf = sf
        self.horizon_s = cfg.ML_HORIZON_S
        self.horizon_bars = cfg.ML_HORIZON_S  # 1 s bars
        self.registry = ModelRegistry(cfg.ML_MODEL_DIR, self.symbol, keep=cfg.ML_KEEP_VERSIONS)
        self.manifest = model_manifest(
            self.horizon_s, self.horizon_bars, cfg.ML_BARRIER_K, cfg.ML_MIN_BARRIER_BPS
        )
        self.store = PredictionStore(sf, self.symbol, enabled=persist)
        self.drift = DriftMonitor(window=cfg.DRIFT_WINDOW, min_n=cfg.DRIFT_MIN_N)
        self._offload: Offload = offload or partial(
            run_isolated, timeout_s=cfg.ML_TRAIN_TIMEOUT_S, threads=cfg.ML_TRAIN_THREADS or None
        )
        self._infer = InferenceWorker(f"infer-{self.symbol}")

        self._bars: deque[Bar] = deque(maxlen=BAR_BUFFER)
        self._closes: deque[float] = deque(maxlen=BAR_BUFFER)
        self._scales = QuantityScales()
        self._index = 0  # bars ingested (global index of the next bar)
        self._last_bar_ts: int | None = None
        self._pending: deque[_Pending] = deque()
        self._X: list[np.ndarray] = []
        self._y: list[int] = []
        self._sample_ts: list[int] = []  # bar time of each labelled sample (for audits/tests)
        self._live: deque[_LivePrediction] = deque()

        self._bundle: TrainResult | None = None
        self._explainer: Explainer | None = None
        self._version = 0
        self._model_id: int | None = None
        self._trained_on = 0
        self._last_train_at: float | None = None
        self._retry_after: float | None = None
        self._train_task: asyncio.Task[None] | None = None
        self._warm_task: asyncio.Task[None] | None = None
        self._last_payload: dict[str, Any] | None = None
        self._last_x: np.ndarray | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.training_runs = 0
        self.sessions = 1  # contiguous segments seen (a gap starts a new one)
        self.last_training_s: float | None = None
        self.last_inference_ms: float | None = None
        self.inference_timeouts = 0

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self, history: Sequence[Bar] = ()) -> None:
        self._loop = asyncio.get_running_loop()
        version, result = await asyncio.to_thread(self.registry.load_latest, self.manifest)
        self._version = version  # a refused artefact still claims its number
        if result is not None:
            model_id = await self.registry.find_id(self._sf, self.registry.path(version))
            self._install(result, version, model_id)
            # It counts as trained on its own samples: the next run waits for fresh ones
            # (and the minimum interval) instead of retraining on every restart.
            self._trained_on = result.n_samples
            self._last_train_at = self._loop.time()
            logger.info(
                "%s: loaded model v%d (%d samples, registry id %s)",
                self.symbol,
                version,
                result.n_samples,
                model_id,
            )
        if history:
            # Seconds of feature vectors for a few thousand bars: a thread, not the loop.
            # Nothing else touches this engine until start() returns.
            await asyncio.to_thread(self._rebuild, history)
            logger.info(
                "%s: rebuilt %d labelled samples from %d persisted bars (%d session%s)",
                self.symbol,
                len(self._X),
                len(history),
                self.sessions,
                "" if self.sessions == 1 else "s",
            )
        await self.store.start()
        self.maybe_train()

    def _rebuild(self, history: Sequence[Bar]) -> None:
        for bar in history:
            self.ingest_bar(bar, live=False)

    async def stop(self) -> None:
        if self._train_task is not None and not self._train_task.done():
            self._train_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._train_task
        await self.store.stop()
        self._infer.shutdown()

    # ── Ingest (event loop; O(LOOKBACK) at worst) ─────────────────

    def ingest_bar(self, bar: Bar, *, live: bool = True) -> InferenceJob | None:
        """
        Bookkeeping for one closed bar: labels that matured, predictions that
        resolved, and the new feature vector. Returns the job to predict (live
        bars with a full lookback only); the prediction itself is `predict()`.
        """
        if self._last_bar_ts is not None and bar.ts_ms - self._last_bar_ts > SESSION_GAP_MS:
            self._new_session()
        self._last_bar_ts = bar.ts_ms
        idx = self._index
        self._index += 1
        self._bars.append(bar)
        self._closes.append(bar.close)
        self._scales.push(bar)
        self._resolve_labels()
        self._resolve_live()

        x = feature_vector(self._bars, self._scales.current())
        if x is None or bar.close <= 0:
            return None
        self._last_x = x
        barrier = barrier_bps(
            bar.volatility_bps, self.horizon_s, self.cfg.ML_BARRIER_K, self.cfg.ML_MIN_BARRIER_BPS
        )
        self._pending.append(_Pending(idx, x, bar.ts_ms, bar.close, barrier))
        if not live:
            return None
        self.maybe_train()
        return InferenceJob(idx, bar.ts_ms, bar.close, barrier, x)

    def _new_session(self) -> None:
        """
        A gap in the bar stream: forget everything whose window would straddle
        it. Labelled samples stay; unresolved labels and predictions cannot be
        resolved honestly and are dropped; the feature lookback starts over.
        """
        self.sessions += 1
        self._bars.clear()
        self._closes.clear()
        self._scales.clear()
        self._pending.clear()
        self._live.clear()
        self._last_x = None

    def _closes_from(self, idx: int) -> list[float] | None:
        pos = idx - (self._index - len(self._closes))
        if pos < 0:
            return None
        return list(self._closes)[pos:]

    def _resolve_labels(self) -> None:
        while self._pending and self._pending[0].idx + self.horizon_bars < self._index:
            p = self._pending.popleft()
            closes = self._closes_from(p.idx)
            if closes is None:
                continue
            lab = triple_barrier(closes, 0, self.horizon_bars, p.barrier)
            if lab is None:
                continue
            self._X.append(p.x)
            self._y.append(lab.cls)
            self._sample_ts.append(p.ts_ms)
        cap = self.cfg.ML_MAX_SAMPLES
        if len(self._X) > cap:
            del self._X[: len(self._X) - cap]
            del self._y[: len(self._y) - cap]
            del self._sample_ts[: len(self._sample_ts) - cap]

    def _resolve_live(self) -> None:
        while self._live and self._live[0].idx + self.horizon_bars < self._index:
            lp = self._live.popleft()
            closes = self._closes_from(lp.idx)
            if closes is None:
                continue
            lab = triple_barrier(closes, 0, self.horizon_bars, lp.barrier)
            if lab is None:
                continue
            self.drift.record(Outcome(lp.ts_ms, lp.p, lp.predicted, lab.cls, lab.realised_bps))
            self.store.resolve(lp, lab.cls, lab.realised_bps)

    # ── Predict (inference thread) ────────────────────────────────

    def _base_payload(self, job: InferenceJob) -> dict[str, Any]:
        b = self._bundle
        return {
            "symbol": self.symbol,
            "ts_ms": job.ts_ms,
            "horizon_s": self.horizon_s,
            "barrier_bps": round(job.barrier, 4),
            "model_version": self._version,
            "calibration": b.calibration if b else None,
            "samples": len(self._X),
            "samples_required": self.cfg.ML_MIN_DATA_POINTS,
            "pending_labels": len(self._pending),
            "training": self.training,
            "drift": self.drift.summary(),
            "timestamp": utcnow().isoformat(),
        }

    async def predict(self, job: InferenceJob) -> dict[str, Any] | None:
        """
        Predict `job` off the event loop. Returns the payload to publish, or
        None when the inference thread did not answer within
        `ML_INFER_TIMEOUT_S` (the bar is skipped rather than queued).
        """
        b = self._bundle  # the model this bar is predicted with, even if a swap lands meanwhile
        empty = {"p_up": None, "p_down": None, "p_flat": None, "predicted_class": None,
                 "confidence": None, "signal": "flat"}  # fmt: skip
        if b is None:
            payload = {**self._base_payload(job), "status": "warming_up", **empty}
            self._last_payload = payload
            return payload
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        try:
            # asyncio.timeout(), not wait_for(): on Python 3.11 wait_for swallows a cancellation
            # that races with the prediction completing (gh-86296), and the intelligence loop
            # then outlived stop() — which waited for it forever.
            async with asyncio.timeout(self.cfg.ML_INFER_TIMEOUT_S):
                probs = await self._infer.run(_predict_proba, b.model, job.x)
        except TimeoutError:
            self.inference_timeouts += 1
            logger.warning(
                "%s: inference exceeded %.1fs; bar skipped",
                self.symbol,
                self.cfg.ML_INFER_TIMEOUT_S,
            )
            return None
        except Exception:
            logger.exception("%s prediction failed", self.symbol)
            return {**self._base_payload(job), "status": "error", **empty}
        self.last_inference_ms = round((loop.time() - t0) * 1000, 2)

        pred = int(np.argmax(probs))
        conf = float(probs[pred])
        thr = self.cfg.ML_SIGNAL_THRESHOLD
        signal = (
            "long"
            if pred == 2 and conf >= thr
            else "short"
            if pred == 0 and conf >= thr
            else "flat"
        )
        lp = _LivePrediction(
            job.idx,
            job.ts_ms,
            job.close,
            job.barrier,
            (float(probs[0]), float(probs[1]), float(probs[2])),
            pred,
        )
        # A gap may have started a new session while this bar was being predicted.
        if job.idx >= self._index - len(self._closes):
            self._live.append(lp)
        self.store.add(lp, self._model_id, self.horizon_s)
        payload = {
            **self._base_payload(job),
            "status": "ready",
            "p_up": round(float(probs[2]), 4),
            "p_down": round(float(probs[0]), 4),
            "p_flat": round(float(probs[1]), 4),
            "predicted_class": CLASS_NAMES[pred],
            "confidence": round(conf, 4),
            "signal": signal,
        }
        self._last_payload = payload
        return payload

    # ── Training (spawned process, single-flight) ─────────────────

    @property
    def training(self) -> bool:
        return self._train_task is not None and not self._train_task.done()

    def training_due(self) -> bool:
        if self.training:
            return False
        n = len(self._X)
        if n < self.cfg.ML_MIN_DATA_POINTS:
            return False
        now = self._loop.time() if self._loop else 0.0
        if self._retry_after is not None and now < self._retry_after:
            return False
        if self._bundle is None:
            return True
        enough_new = n >= self._trained_on + self.cfg.ML_RETRAIN_EVERY_SAMPLES
        waited = (
            self._last_train_at is None
            or now - self._last_train_at >= self.cfg.ML_RETRAIN_MIN_INTERVAL_S
        )
        return enough_new and waited

    def maybe_train(self) -> bool:
        if self._loop is None or not self.training_due():
            return False
        X = np.asarray(self._X)
        y = np.asarray(self._y)
        self._train_task = self._loop.create_task(self._train(X, y), name=f"train-{self.symbol}")
        return True

    async def _train(self, X: np.ndarray, y: np.ndarray) -> None:
        """One training run end to end — fit, save, register, swap — so nothing can re-trigger it midway."""
        loop = asyncio.get_running_loop()
        n = len(X)
        t0 = loop.time()
        try:
            result: TrainResult | None = await self._offload(
                train, X, y, FEATURE_NAMES, self.horizon_bars, self.horizon_s
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s training failed", self.symbol)
            self._retry_after = loop.time() + self.cfg.ML_TRAIN_RETRY_S
            return
        self.last_training_s = round(loop.time() - t0, 2)
        if result is None:
            logger.info("%s: training declined (insufficient class variety)", self.symbol)
            self._retry_after = loop.time() + self.cfg.ML_TRAIN_RETRY_S
            return
        result.manifest = self.manifest
        version = self._version + 1
        path = await asyncio.to_thread(self.registry.save, result, version)
        model_id = await self.registry.record(self._sf, result, version, path)
        self._install(result, version, model_id)
        self._trained_on = n
        self._last_train_at = loop.time()
        self._retry_after = None
        self.training_runs += 1
        logger.info(
            "%s: model v%d installed (%d samples, %.1fs, oos=%s)",
            self.symbol,
            version,
            n,
            self.last_training_s,
            result.oos,
        )

    def _install(self, result: TrainResult, version: int, model_id: int | None) -> None:
        self._bundle = result  # atomic reference swap
        self._version = version
        self._model_id = model_id
        self._explainer = Explainer(result.model, result.base_models, result.feature_names)
        oos = result.oos
        self.drift.reset_baseline(
            result.class_prior, oos.get("log_loss"), oos.get("prior_log_loss")
        )
        if self._loop is not None:  # build the SHAP explainers now, off the loop
            self._warm_task = self._loop.create_task(self._warm(self._explainer))

    async def _warm(self, explainer: Explainer) -> None:
        # One build per inference-thread task, so a prediction waits behind at most one.
        for i in range(explainer.size):
            if explainer is not self._explainer:
                return  # a newer model was installed meanwhile
            await self._infer.run(explainer.warm, i)

    # ── Reads ─────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        return self._bundle is not None

    @property
    def version(self) -> int:
        return self._version

    @property
    def samples(self) -> int:
        return len(self._X)

    def last_payload(self) -> dict[str, Any] | None:
        return self._last_payload

    async def explain(self) -> dict[str, Any] | None:
        """SHAP contributions for the latest feature vector (computed on the inference thread)."""
        if self._explainer is None or self._last_x is None:
            return None
        return await self._infer.run(self._explainer.explain, self._last_x)

    def model_info(self) -> dict[str, Any]:
        b = self._bundle
        n = len(self._X)
        return {
            "symbol": self.symbol,
            "status": "ready" if b else ("training" if self.training else "warming_up"),
            "model_version": self._version,
            "model_id": self._model_id,
            "trained_at": b.trained_at.isoformat() if b else None,
            "training_samples": b.n_samples if b else 0,
            "samples_available": n,
            "samples_required": self.cfg.ML_MIN_DATA_POINTS,
            "pending_labels": len(self._pending),
            "horizon_s": self.horizon_s,
            "lookback_bars": LOOKBACK,
            "barrier_k": self.cfg.ML_BARRIER_K,
            "calibration": b.calibration if b else None,
            "metrics": b.metrics_payload() if b else {"oos": {}, "folds": []},
            "class_prior": b.class_prior if b else {},
            "feature_importance": b.importance if b else {},
            "feature_importance_std": b.importance_std if b else {},
            "feature_names": list(FEATURE_NAMES),
            "hyperparameters": b.hyperparameters if b else {},
            "next_retrain_in_samples": (
                max(self._trained_on + self.cfg.ML_RETRAIN_EVERY_SAMPLES - n, 0)
                if b
                else max(self.cfg.ML_MIN_DATA_POINTS - n, 0)
            ),
            "training_runs": self.training_runs,
            "drift": self.drift.summary(),
            "predictions_persisted": self.store.written,
            "predictions_resolved": self.store.resolved,
        }

    def runtime_stats(self) -> dict[str, Any]:
        """Timings and counters for /system/metrics."""
        return {
            "training": self.training,
            "last_training_s": self.last_training_s,
            "last_inference_ms": self.last_inference_ms,
            "inference_timeouts": self.inference_timeouts,
            "sessions": self.sessions,
            "prediction_backlog": self.store.backlog,
            "prediction_failed_flushes": self.store.failed_flushes,
        }
