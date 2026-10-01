"""
Regime detection
================

Two separate, honest axes.

**Volatility state** — a 4-state Gaussian HMM over 1-second bars of
`[log_return, |log_return|, spread_z, ofi_z, vol_z]`, refit periodically in
a worker process and decoded by forward filtering on the trailing window. The
HMM provides *persistent segmentation*; each state's **label** comes from its
learned mean `vol_z` against the adaptive baseline (calm < −0.25 σ ≤ normal
< 1 σ ≤ elevated < 2.25 σ ≤ extreme). Labels therefore have an absolute
meaning, may repeat across states (a single-regime window is honestly "all
normal"), and state posteriors are aggregated per label. Until enough bars
exist the state comes from the same `vol_z` cut-points and says so
(`source="fallback"`).

**Trend** — the drift of the last two minutes of 1-second log-returns as a
t-statistic with a Newey–West (HAC) standard error, because 1-second returns
are autocorrelated (bid–ask bounce) and a plain t-test overstates
significance. The trend is "up" or "down" only while |t| clears 2 (it
releases below 1.5, so it doesn't flicker at the threshold) and "flat"
otherwise; `direction = tanh(t / 2)` is the continuous read-out. A market is
called *trending* only when this trend is significant.

Fitting runs in a worker process (`fit_regime`); the detector only decides
*when* (`needs_refit` → `mark_refit_started`) and installs the result.
"""

from __future__ import annotations

import logging
import math
import warnings
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from algoviz.market.bars import REGIME_LABELS, SESSION_GAP_MS, Bar

logger = logging.getLogger("algoviz.regime")
# hmmlearn reports EM non-convergence through its logger on every refit; the
# fitted model is still usable (we cap n_iter deliberately), so keep it quiet.
logging.getLogger("hmmlearn").setLevel(logging.ERROR)

LABELS: tuple[str, ...] = REGIME_LABELS
N_STATES = 4
FIRST_FIT_RETRY_BARS = 60

TREND_WINDOW = 120  # 1 s returns behind the trend statistic
TREND_LAGS = 5  # Newey–West bandwidth
TREND_ENTER_T = 2.0
TREND_EXIT_T = 1.5


@dataclass(slots=True)
class RegimeState:
    label: str  # volatility state
    direction: float  # −1 … +1, tanh(t / 2)
    trend: str  # down | flat | up
    trend_t: float  # HAC t-statistic of the drift
    probs: dict[str, float]
    source: str  # hmm | fallback
    model_version: int
    bars_seen: int


@dataclass(slots=True)
class _Fitted:
    model: Any
    mean: np.ndarray
    std: np.ndarray
    state_labels: list[str]  # state index → label
    version: int
    bars: int
    log_likelihood: float


VOL_Z_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (-0.25, "calm"),
    (1.0, "normal"),
    (2.25, "elevated"),
)


def label_for_vol_z(vol_z: float) -> str:
    for upper, label in VOL_Z_THRESHOLDS:
        if vol_z < upper:
            return label
    return "extreme"


def hac_t_stat(returns: np.ndarray, lags: int = TREND_LAGS) -> float:
    """t-statistic of the mean with a Newey–West (Bartlett-kernel) long-run variance."""
    n = len(returns)
    if n < 2 * lags + 2:
        return 0.0
    d = returns - returns.mean()
    lrv = float(d @ d) / n
    for lag in range(1, lags + 1):
        lrv += 2.0 * (1.0 - lag / (lags + 1)) * float(d[lag:] @ d[:-lag]) / n
    if lrv <= 1e-24:
        return 0.0
    return float(returns.mean() / math.sqrt(lrv / n))


class TrendTracker:
    """The drift's HAC t-statistic over a rolling window, labelled with hysteresis."""

    def __init__(self, window: int = TREND_WINDOW) -> None:
        self._returns: deque[float] = deque(maxlen=window)
        self.t = 0.0
        self.label = "flat"

    def push(self, r: float) -> str:
        self._returns.append(r)
        self.t = hac_t_stat(np.asarray(self._returns))
        if self.label == "flat" and abs(self.t) >= TREND_ENTER_T:
            self.label = "up" if self.t > 0 else "down"
        elif self.label != "flat" and (
            abs(self.t) < TREND_EXIT_T or (self.t > 0) != (self.label == "up")
        ):
            self.label = "flat"
        return self.label

    def clear(self) -> None:
        self._returns.clear()
        self.t = 0.0
        self.label = "flat"


def _bar_row(bar: Bar, prev_close: float | None) -> list[float]:
    r = math.log(bar.close / prev_close) if prev_close and bar.close > 0 and prev_close > 0 else 0.0
    return [r, abs(r), bar.spread_z or 0.0, bar.ofi_z or 0.0, bar.vol_z or 0.0]


class RegimeDetector:
    def __init__(
        self,
        *,
        window_bars: int = 1800,
        min_bars: int = 300,
        refit_every_bars: int = 300,
        decode_window: int = 120,
        min_dwell_bars: int = 5,
        confident_switch: float = 0.9,
    ) -> None:
        self._rows: deque[list[float]] = deque(maxlen=window_bars)
        self._prev_close: float | None = None
        self._prev_ts: int | None = None
        self._min_bars = min_bars
        self._refit_every = refit_every_bars
        self._decode_window = decode_window
        self._min_dwell = min_dwell_bars
        self._confident = confident_switch
        self._fitted: _Fitted | None = None
        self._bars_since_fit = 0
        self._fit_attempts = 0
        self._refit_pending = False
        self._label = "calm"
        self._candidate: str | None = None
        self._candidate_n = 0
        self._probs = {lab: 0.25 for lab in LABELS}
        self._trend = TrendTracker()
        self.bars_seen = 0

    # ── Input ─────────────────────────────────────────────────────

    def push_bar(self, bar: Bar) -> RegimeState:
        if self._prev_ts is not None and bar.ts_ms - self._prev_ts > SESSION_GAP_MS:
            self._prev_close = None  # no return across an outage: it would read as a shock
            self._trend.clear()  # and no drift measured across it
        self._prev_ts = bar.ts_ms
        row = _bar_row(bar, self._prev_close)
        self._prev_close = bar.close if bar.close > 0 else self._prev_close
        self._rows.append(row)
        self._trend.push(row[0])
        self.bars_seen += 1
        self._bars_since_fit += 1

        if self._fitted is None:
            fallback = label_for_vol_z(bar.vol_z or 0.0)
            self._apply_label(fallback, {}, confident=False)
            self._probs = {lab: (1.0 if lab == self._label else 0.0) for lab in LABELS}
            return self.current()
        try:
            self._decode()
        except Exception:
            logger.exception("regime decode failed; keeping previous label")
        return self.current()

    def needs_refit(self) -> bool:
        if self._refit_pending or len(self._rows) < self._min_bars:
            return False
        if self._fitted is None:  # first fit: now, or retry a failed one after a short wait
            return self._fit_attempts == 0 or self._bars_since_fit >= FIRST_FIT_RETRY_BARS
        return self._bars_since_fit >= self._refit_every

    def mark_refit_started(self) -> None:
        """Called when a fit is submitted, so bars arriving meanwhile don't request another."""
        self._bars_since_fit = 0
        self._fit_attempts += 1
        self._refit_pending = True

    def refit_finished(self) -> None:
        self._refit_pending = False

    def training_matrix(self) -> np.ndarray:
        return np.asarray(self._rows, dtype=np.float64)

    # ── Fit (runs in a worker process via fit_regime) ────────────

    @staticmethod
    def fit(X: np.ndarray, version: int, seed: int = 7) -> _Fitted | None:
        from hmmlearn.hmm import GaussianHMM

        if len(X) < N_STATES * 20:
            return None
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std[std < 1e-9] = 1.0
        Z = (X - mean) / std
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = GaussianHMM(
                n_components=N_STATES,
                covariance_type="diag",
                n_iter=60,
                tol=1e-3,
                random_state=seed,
                min_covar=1e-3,
            )
            model.fit(Z)
        # Label each state by its mean vol_z in original units (feature 4).
        vol_z_means = model.means_[:, 4] * std[4] + mean[4]
        state_labels = [label_for_vol_z(float(v)) for v in vol_z_means]
        ll = float(model.score(Z))
        return _Fitted(model, mean, std, state_labels, version, len(X), ll)

    def install(self, fitted: _Fitted | None) -> None:
        if fitted is None:
            return
        self._fitted = fitted
        logger.info(
            "regime HMM v%d fitted on %d bars (loglik %.1f, states=%s)",
            fitted.version,
            fitted.bars,
            fitted.log_likelihood,
            fitted.state_labels,
        )

    # ── Decode ────────────────────────────────────────────────────

    def _decode(self) -> None:
        f = self._fitted
        assert f is not None
        n = min(self._decode_window, len(self._rows))
        X = np.asarray(list(self._rows)[-n:], dtype=np.float64)
        Z = (X - f.mean) / f.std
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            post = f.model.predict_proba(Z)[-1]
        probs = dict.fromkeys(LABELS, 0.0)
        for state, label in enumerate(f.state_labels):
            probs[label] += float(post[state])
        best = max(probs, key=probs.get)  # type: ignore[arg-type]
        self._apply_label(best, probs, confident=probs[best] >= self._confident)

    def _apply_label(self, label: str, probs: dict[str, float], confident: bool) -> None:
        if probs:
            self._probs = probs
        if label == self._label:
            self._candidate, self._candidate_n = None, 0
            return
        if confident:
            self._label, self._candidate, self._candidate_n = label, None, 0
            return
        if self._candidate == label:
            self._candidate_n += 1
        else:
            self._candidate, self._candidate_n = label, 1
        if self._candidate_n >= self._min_dwell:
            self._label, self._candidate, self._candidate_n = label, None, 0

    # ── Output ────────────────────────────────────────────────────

    def current(self) -> RegimeState:
        f = self._fitted
        return RegimeState(
            label=self._label,
            direction=round(math.tanh(self._trend.t / 2.0), 4),
            trend=self._trend.label,
            trend_t=round(self._trend.t, 3),
            probs={k: round(v, 4) for k, v in self._probs.items()},
            source="hmm" if f else "fallback",
            model_version=f.version if f else 0,
            bars_seen=self.bars_seen,
        )

    @property
    def model_version(self) -> int:
        return self._fitted.version if self._fitted else 0


def fit_regime(X: np.ndarray, version: int) -> _Fitted | None:
    """Module-level entry point so a spawned worker process can import and run the fit."""
    return RegimeDetector.fit(X, version)
