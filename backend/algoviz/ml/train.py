"""
Training
========

**Evaluate what we serve.** One recipe, `fit_model`, builds both the served
model and every walk-forward fold model:

1. gradient-boosted trees whose early stopping validates on the time-ordered
   tail of the training window (after an embargo), never a random split;
2. probability calibration on embargoed time splits of the same window
   (`CalibratedClassifierCV` over `TimeSeriesSplit(gap=horizon)`, one
   calibrated tree model per split, averaged).

Walk-forward evaluation runs the recipe inside each training window of
`TimeSeriesSplit(gap=horizon)` — the gap is the embargo that keeps a training
label's forward window out of the test fold — and scores the calibrated fold
model on the held-out fold. Per fold: accuracy, log-loss (calibrated and
raw), the multiclass Brier score with its reliability / resolution /
uncertainty decomposition, a reliability curve, and the same scores for two
baselines: the class prior and a regularised logistic regression on clipped
standardised features. "Edge" is the log-loss improvement over the prior.

Permutation importance is measured on held-out folds with the fold's own
served model and scored on log-loss: the increase in held-out log-loss when a
feature's values are shuffled.

Runs in a spawned worker process; returns a `TrainResult` the engine swaps in
atomically.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from algoviz.core.time import utcnow
from algoviz.ml.evaluation import (
    Curve,
    brier_decomposition,
    calibration_error,
    pool_curves,
    reliability_curve,
    summarise_curve,
)
from algoviz.ml.labels import CLASS_NAMES

logger = logging.getLogger("algoviz.ml.train")

CLASSES = np.array([0, 1, 2])
N_SPLITS = 4
MIN_PER_FOLD = 40

HGB_PARAMS: dict[str, Any] = {
    "learning_rate": 0.06,
    "max_iter": 300,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 25,
    "l2_regularization": 1.0,
    "n_iter_no_change": 20,
}
ES_TAIL = 0.15  # share of a training window held back (time-ordered) for early stopping
ES_MIN_VAL = 50  # smaller tails are too noisy to stop on …
ES_FALLBACK_ITER = 60  # … so the model trains a fixed, short ensemble instead

CAL_SPLITS = 3
CAL_MIN = 400  # below this a window is too short to split for calibration
ISOTONIC_MIN = 1000  # isotonic needs data; sigmoid (Platt) is the small-sample choice

LOGISTIC_C = 0.1
CLIP_SIGMA = 5.0  # standardised inputs are clipped so a heavy-tailed feature can't blow it up

IMPORTANCE_FOLDS = 2  # the most recent folds (largest training windows)
IMPORTANCE_ROWS = 1500  # evenly spaced rows of a test fold, to bound the cost
IMPORTANCE_REPEATS = 3
IMPORTANCE_TOP = 20


# ── The served recipe ─────────────────────────────────────────────


class TailStoppedHGB(ClassifierMixin, BaseEstimator):
    """
    Histogram gradient boosting whose early stopping validates on the last
    `ES_TAIL` of its (time-ordered) training window, `gap` rows after the fit
    rows, instead of HGB's built-in random split — which would let the model
    stop on rows interleaved with, and so leaking into, its training rows.
    """

    def __init__(self, gap: int = 0, seed: int = 7) -> None:
        self.gap = gap
        self.seed = seed

    def fit(self, X: np.ndarray, y: np.ndarray) -> TailStoppedHGB:
        n = len(X)
        n_val = int(n * ES_TAIL)
        fit_end = n - n_val - self.gap
        head = y[:fit_end] if fit_end > 0 else y[:0]
        if n_val >= ES_MIN_VAL and len(np.unique(head)) >= 2:
            val_X, val_y = X[n - n_val :], y[n - n_val :]
            seen = np.isin(val_y, np.unique(head))  # a class the head never saw can't be scored
            model = HistGradientBoostingClassifier(
                **HGB_PARAMS, early_stopping=True, random_state=self.seed
            ).fit(X[:fit_end], head, X_val=val_X[seen], y_val=val_y[seen])
        else:
            model = HistGradientBoostingClassifier(
                **(HGB_PARAMS | {"max_iter": ES_FALLBACK_ITER}),
                early_stopping=False,
                random_state=self.seed,
            ).fit(X, y)
        self.model_ = model
        self.classes_ = model.classes_
        self.n_iter_ = int(model.n_iter_)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.model_.predict_proba(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model_.predict(X)


def fit_model(X: np.ndarray, y: np.ndarray, gap: int, seed: int = 7) -> tuple[Any, str]:
    """The served recipe on one training window. Returns the model and its calibration method."""
    n = len(X)
    if n >= CAL_MIN:
        method = "isotonic" if n >= ISOTONIC_MIN else "sigmoid"
        calibrated = CalibratedClassifierCV(
            estimator=TailStoppedHGB(gap=gap, seed=seed),
            method=method,
            cv=TimeSeriesSplit(n_splits=CAL_SPLITS, gap=gap),
            ensemble=True,
        )
        try:
            return calibrated.fit(X, y), method
        except ValueError as exc:  # a calibration split lacked a class
            logger.warning("calibration failed (%s); serving the uncalibrated model", exc)
    return TailStoppedHGB(gap=gap, seed=seed).fit(X, y), "none"


def base_estimators(model: Any) -> list[TailStoppedHGB]:
    """The tree models inside a served model (one per calibration split, or the model itself)."""
    if isinstance(model, CalibratedClassifierCV):
        return [c.estimator for c in model.calibrated_classifiers_]
    return [model]


def _align_proba(model: Any, X: np.ndarray) -> np.ndarray:
    """predict_proba aligned to the fixed class order [0, 1, 2] even if a class is absent."""
    p = model.predict_proba(X)
    out = np.full((len(X), 3), 1e-6)
    for j, c in enumerate(model.classes_):
        out[:, int(c)] = p[:, j]
    return out / out.sum(axis=1, keepdims=True)


def _raw_proba(model: Any, X: np.ndarray) -> np.ndarray:
    """The served model's tree models before calibration, averaged."""
    return np.mean([_align_proba(m, X) for m in base_estimators(model)], axis=0)


def _clip(Z: np.ndarray) -> np.ndarray:
    return np.clip(Z, -CLIP_SIGMA, CLIP_SIGMA)


def _logistic() -> Any:
    return make_pipeline(
        StandardScaler(),
        FunctionTransformer(_clip),
        LogisticRegression(C=LOGISTIC_C, max_iter=1000),
    )


def _prior_proba(y_train: np.ndarray, n: int) -> np.ndarray:
    counts = np.bincount(y_train, minlength=3).astype(float) + 1.0  # Laplace
    p = counts / counts.sum()
    return np.tile(p, (n, 1))


def _neg_log_loss(model: Any, X: np.ndarray, y: np.ndarray) -> float:
    return -float(log_loss(y, _align_proba(model, X), labels=CLASSES))


# ── Results ───────────────────────────────────────────────────────


@dataclass(slots=True)
class FoldMetrics:
    n_train: int
    n_test: int
    accuracy: float
    log_loss: float
    raw_log_loss: float
    brier: float
    brier_reliability: float
    brier_resolution: float
    brier_uncertainty: float
    prior_log_loss: float
    logistic_log_loss: float
    logistic_accuracy: float
    calibration: str
    reliability: Curve = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_train": self.n_train,
            "n_test": self.n_test,
            "accuracy": round(self.accuracy, 4),
            "log_loss": round(self.log_loss, 4),
            "raw_log_loss": round(self.raw_log_loss, 4),
            "brier": round(self.brier, 4),
            "brier_reliability": round(self.brier_reliability, 5),
            "brier_resolution": round(self.brier_resolution, 5),
            "brier_uncertainty": round(self.brier_uncertainty, 5),
            "prior_log_loss": round(self.prior_log_loss, 4),
            "logistic_log_loss": round(self.logistic_log_loss, 4),
            "logistic_accuracy": round(self.logistic_accuracy, 4),
            "calibration": self.calibration,
            "reliability": self.reliability,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FoldMetrics:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


_MEAN_KEYS = (
    "accuracy",
    "log_loss",
    "raw_log_loss",
    "brier",
    "brier_reliability",
    "brier_resolution",
    "brier_uncertainty",
    "prior_log_loss",
    "logistic_log_loss",
    "logistic_accuracy",
)


@dataclass(slots=True)
class TrainResult:
    model: Any  # the served model: calibrated tree ensemble (or a single tree model)
    base_models: list[Any]  # its tree models before calibration — what SHAP explains
    feature_names: tuple[str, ...]
    n_samples: int
    horizon_s: int
    trained_at: datetime
    folds: list[FoldMetrics]
    importance: dict[str, float]  # held-out log-loss increase when the feature is shuffled
    importance_std: dict[str, float]
    class_prior: dict[str, float]
    calibration: str
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)  # set by the engine; checked on load

    # ── Aggregates ────────────────────────────────────────────────

    @property
    def oos(self) -> dict[str, float]:
        if not self.folds:
            return {}
        agg = {k: float(np.mean([getattr(f, k) for f in self.folds])) for k in _MEAN_KEYS}
        agg["edge_vs_prior"] = agg["prior_log_loss"] - agg["log_loss"]
        agg["edge_vs_logistic"] = agg["logistic_log_loss"] - agg["log_loss"]
        agg["calibration_gain"] = agg["raw_log_loss"] - agg["log_loss"]
        ece = calibration_error(self.reliability)
        if ece is not None:
            agg["calibration_error"] = ece
        agg["n_folds"] = float(len(self.folds))
        return {k: round(v, 5 if k.startswith("brier_") else 4) for k, v in agg.items()}

    @property
    def reliability(self) -> Curve:
        """The held-out reliability curve pooled over every fold."""
        return pool_curves(f.reliability for f in self.folds)

    def metrics_payload(self) -> dict[str, Any]:
        """The API / registry shape: reliability bins as objects, empty bins left out."""
        return {
            "oos": self.oos,
            "folds": [
                f.as_dict() | {"reliability": summarise_curve(f.reliability)} for f in self.folds
            ],
            "reliability": summarise_curve(self.reliability) if self.folds else None,
        }


# ── Training ──────────────────────────────────────────────────────


def _evenly_spaced(n: int, k: int) -> np.ndarray:
    return np.arange(n) if n <= k else np.linspace(0, n - 1, k).astype(int)


def train(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: tuple[str, ...],
    horizon_bars: int,
    horizon_s: int,
    *,
    seed: int = 7,
) -> TrainResult | None:
    n = len(X)
    if n < MIN_PER_FOLD * 3 or len(np.unique(y)) < 2:
        return None

    folds: list[FoldMetrics] = []
    held_out: list[tuple[Any, np.ndarray, np.ndarray]] = []  # (fold model, X_test, y_test)
    n_splits = max(2, min(N_SPLITS, n // (MIN_PER_FOLD * 2)))
    outer = TimeSeriesSplit(n_splits=n_splits, gap=horizon_bars)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for tr, te in outer.split(X):
            if len(np.unique(y[tr])) < 2:
                continue
            model, method = fit_model(X[tr], y[tr], horizon_bars, seed)
            yt = y[te]
            p = _align_proba(model, X[te])
            p_raw = _raw_proba(model, X[te])
            p_lr = _align_proba(_logistic().fit(X[tr], y[tr]), X[te])
            p_prior = _prior_proba(y[tr], len(te))
            dec = brier_decomposition(p, yt)
            folds.append(
                FoldMetrics(
                    n_train=len(tr),
                    n_test=len(te),
                    accuracy=float(accuracy_score(yt, p.argmax(axis=1))),
                    log_loss=float(log_loss(yt, p, labels=CLASSES)),
                    raw_log_loss=float(log_loss(yt, p_raw, labels=CLASSES)),
                    brier=dec["brier"],
                    brier_reliability=dec["reliability"],
                    brier_resolution=dec["resolution"],
                    brier_uncertainty=dec["uncertainty"],
                    prior_log_loss=float(log_loss(yt, p_prior, labels=CLASSES)),
                    logistic_log_loss=float(log_loss(yt, p_lr, labels=CLASSES)),
                    logistic_accuracy=float(accuracy_score(yt, p_lr.argmax(axis=1))),
                    calibration=method,
                    reliability=reliability_curve(p, yt),
                )
            )
            held_out.append((model, X[te], yt))

        # Held-out permutation importance: the fold's own served model, scored on log-loss.
        drops: list[np.ndarray] = []
        for model, Xt, yt in held_out[-IMPORTANCE_FOLDS:]:
            if len(yt) < MIN_PER_FOLD:
                continue
            rows = _evenly_spaced(len(yt), IMPORTANCE_ROWS)
            pi = permutation_importance(
                model,
                Xt[rows],
                yt[rows],
                scoring=_neg_log_loss,
                n_repeats=IMPORTANCE_REPEATS,
                random_state=seed,
            )
            drops.append(pi.importances)  # (features, repeats): the rise in log-loss
        importance: dict[str, float] = {}
        importance_std: dict[str, float] = {}
        if drops:
            all_drops = np.concatenate(drops, axis=1)
            mean, std = all_drops.mean(axis=1), all_drops.std(axis=1)
            for i in np.argsort(mean)[::-1][:IMPORTANCE_TOP]:
                if mean[i] > 0:
                    importance[feature_names[i]] = round(float(mean[i]), 5)
                    importance_std[feature_names[i]] = round(float(std[i]), 5)

        # The served model: the same recipe on everything.
        model, method = fit_model(X, y, horizon_bars, seed)

    bases = base_estimators(model)
    counts = np.bincount(y, minlength=3).astype(float)
    prior = {CLASS_NAMES[i]: round(float(counts[i] / counts.sum()), 4) for i in range(3)}
    result = TrainResult(
        model=model,
        base_models=[b.model_ for b in bases],
        feature_names=feature_names,
        n_samples=n,
        horizon_s=horizon_s,
        trained_at=utcnow(),
        folds=folds,
        importance=importance,
        importance_std=importance_std,
        class_prior=prior,
        calibration=method,
        hyperparameters={
            "model": "HistGradientBoostingClassifier",
            **HGB_PARAMS,
            "early_stopping": f"time-ordered tail {ES_TAIL:.0%}, embargo {horizon_bars}",
            "n_iter": [b.n_iter_ for b in bases],
            "calibration_cv": f"TimeSeriesSplit(n_splits={CAL_SPLITS}, gap={horizon_bars})",
            "cv": f"TimeSeriesSplit(n_splits={n_splits}, gap={horizon_bars})",
            "logistic_baseline": f"C={LOGISTIC_C}, inputs clipped at ±{CLIP_SIGMA:g}σ",
        },
    )
    logger.info("trained on %d samples: oos=%s prior=%s", n, result.oos, prior)
    return result
