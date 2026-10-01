"""
Probabilistic evaluation
========================

Scores for class probabilities in the fixed [down, flat, up] order.

- **Reliability curve** — per class, the forecasts are binned into equal-width
  probability bins; each bin records its count, mean forecast and observed
  frequency. A calibrated model's bins sit on the diagonal. Curves from
  several folds pool exactly (count-weighted).
- **Brier decomposition** (Murphy) — per class on the same bins, summed over
  classes:

      Brier ≈ reliability − resolution + uncertainty

  *reliability* is miscalibration (0 is perfect), *resolution* is how far the
  binned forecasts move away from the base rate (higher is better) and
  *uncertainty* is the base rate's own variance — a property of the data, not
  of the model. With binned forecasts the identity holds up to a within-bin
  term, which is small for 10 bins and reported as the remainder.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from algoviz.ml.labels import CLASS_NAMES

N_BINS = 10

# One bin: [count, mean forecast, observed frequency]; empty bins are [0, 0, 0].
Curve = dict[str, list[list[float]]]


def _bin_index(p: np.ndarray, n_bins: int) -> np.ndarray:
    return np.minimum((p * n_bins).astype(int), n_bins - 1)


def reliability_curve(proba: np.ndarray, y: np.ndarray, n_bins: int = N_BINS) -> Curve:
    """Per class: the fixed bins of forecast probability with count, mean forecast and hit rate."""
    out: Curve = {}
    for c, name in enumerate(CLASS_NAMES):
        p = proba[:, c]
        hit = (y == c).astype(float)
        idx = _bin_index(p, n_bins)
        n = np.bincount(idx, minlength=n_bins).astype(float)
        f = np.bincount(idx, weights=p, minlength=n_bins)
        o = np.bincount(idx, weights=hit, minlength=n_bins)
        safe = np.maximum(n, 1.0)
        out[name] = [
            [int(n[k]), round(float(f[k] / safe[k]), 5), round(float(o[k] / safe[k]), 5)]
            for k in range(n_bins)
        ]
    return out


def pool_curves(curves: Iterable[Curve]) -> Curve:
    """Count-weighted union of reliability curves over the same bins."""
    pooled: dict[str, np.ndarray] = {}
    for curve in curves:
        for name, bins in curve.items():
            arr = np.asarray(bins, dtype=float)
            sums = np.column_stack([arr[:, 0], arr[:, 0] * arr[:, 1], arr[:, 0] * arr[:, 2]])
            pooled[name] = pooled[name] + sums if name in pooled else sums
    out: Curve = {}
    for name, s in pooled.items():
        safe = np.maximum(s[:, 0], 1.0)
        out[name] = [
            [int(s[k, 0]), round(float(s[k, 1] / safe[k]), 5), round(float(s[k, 2] / safe[k]), 5)]
            for k in range(len(s))
        ]
    return out


def brier_decomposition(proba: np.ndarray, y: np.ndarray, n_bins: int = N_BINS) -> dict[str, float]:
    """Multiclass Brier score and its binned reliability / resolution / uncertainty terms."""
    n = len(y)
    rel = res = unc = 0.0
    for c in range(proba.shape[1]):
        p = proba[:, c]
        hit = (y == c).astype(float)
        base = float(hit.mean())
        idx = _bin_index(p, n_bins)
        cnt = np.bincount(idx, minlength=n_bins).astype(float)
        f = np.bincount(idx, weights=p, minlength=n_bins)
        o = np.bincount(idx, weights=hit, minlength=n_bins)
        used = cnt > 0
        fbar, obar = f[used] / cnt[used], o[used] / cnt[used]
        rel += float((cnt[used] * (fbar - obar) ** 2).sum() / n)
        res += float((cnt[used] * (obar - base) ** 2).sum() / n)
        unc += base * (1.0 - base)
    onehot = np.zeros_like(proba)
    onehot[np.arange(n), y] = 1.0
    brier = float(((proba - onehot) ** 2).sum(axis=1).mean())
    return {"brier": brier, "reliability": rel, "resolution": res, "uncertainty": unc}


def calibration_error(curve: Curve) -> float | None:
    """Count-weighted mean |forecast − observed| over every class's bins (the pooled ECE)."""
    total = err = 0.0
    for bins in curve.values():
        for n, f, o in bins:
            total += n
            err += n * abs(f - o)
    return err / total if total > 0 else None


def summarise_curve(curve: Curve) -> dict[str, Any]:
    """The JSON shape the API returns: per class, only the bins that hold forecasts."""
    return {
        name: [{"n": int(n), "forecast": f, "observed": o} for n, f, o in bins if n > 0]
        for name, bins in curve.items()
    }
