"""
Drift monitor
=============

Every live prediction is resolved once its horizon elapses. Over a rolling
window this yields realised hit-rate, log-loss and Brier score that can be
compared with (a) the class-prior baseline and (b) the model's own
walk-forward numbers at training time. When realised log-loss stops beating
the prior, the model has no edge — the UI says so, and a signal fires.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

Status = str  # no_data | edge | no_edge | decayed


@dataclass(slots=True)
class Outcome:
    ts_ms: int
    p: tuple[float, float, float]  # down, flat, up
    predicted: int
    realised: int
    realised_bps: float


class DriftMonitor:
    def __init__(self, *, window: int = 300, min_n: int = 40) -> None:
        self.window = window
        self.min_n = min_n
        self._outcomes: deque[Outcome] = deque(maxlen=window)
        self._prior: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)
        self._train_log_loss: float | None = None
        self._train_prior_log_loss: float | None = None
        self.total_resolved = 0

    def reset_baseline(
        self,
        class_prior: dict[str, float],
        oos_log_loss: float | None,
        oos_prior_log_loss: float | None,
    ) -> None:
        self._prior = (
            class_prior.get("down", 1 / 3),
            class_prior.get("flat", 1 / 3),
            class_prior.get("up", 1 / 3),
        )
        self._train_log_loss = oos_log_loss
        self._train_prior_log_loss = oos_prior_log_loss
        self._outcomes.clear()

    def record(self, outcome: Outcome) -> None:
        self._outcomes.append(outcome)
        self.total_resolved += 1

    # ── Metrics ───────────────────────────────────────────────────

    @staticmethod
    def _log_loss(ps: np.ndarray, ys: np.ndarray) -> float:
        p = np.clip(ps[np.arange(len(ys)), ys], 1e-6, 1.0)
        return float(-np.log(p).mean())

    def summary(self) -> dict[str, Any]:
        n = len(self._outcomes)
        if n < self.min_n:
            return {
                "status": "no_data",
                "n": n,
                "n_required": self.min_n,
                "total_resolved": self.total_resolved,
            }
        ps = np.asarray([o.p for o in self._outcomes])
        ys = np.asarray([o.realised for o in self._outcomes])
        preds = np.asarray([o.predicted for o in self._outcomes])
        onehot = np.zeros_like(ps)
        onehot[np.arange(n), ys] = 1.0
        ll = self._log_loss(ps, ys)
        prior = np.tile(self._prior, (n, 1))
        ll_prior = self._log_loss(prior, ys)
        edge = ll_prior - ll
        hit = float((preds == ys).mean())
        # directional hit-rate ignores flats: of the up/down calls, how many were right?
        directional = (preds != 1) & (ys != 1)
        dir_hit = (
            float((preds[directional] == ys[directional]).mean()) if directional.any() else None
        )
        if edge <= 0:
            status: Status = "no_edge"
        elif self._train_log_loss is not None and ll > self._train_log_loss * 1.15:
            status = "decayed"
        else:
            status = "edge"
        return {
            "status": status,
            "n": n,
            "n_required": self.min_n,
            "total_resolved": self.total_resolved,
            "hit_rate": round(hit, 4),
            "directional_hit_rate": round(dir_hit, 4) if dir_hit is not None else None,
            "log_loss": round(ll, 4),
            "prior_log_loss": round(ll_prior, 4),
            "edge_vs_prior": round(edge, 4),
            "brier": round(float(((ps - onehot) ** 2).sum(axis=1).mean()), 4),
            "train_log_loss": round(self._train_log_loss, 4) if self._train_log_loss else None,
            "train_prior_log_loss": (
                round(self._train_prior_log_loss, 4) if self._train_prior_log_loss else None
            ),
            "realised_class_mix": {
                "down": round(float((ys == 0).mean()), 3),
                "flat": round(float((ys == 1).mean()), 3),
                "up": round(float((ys == 2).mean()), 3),
            },
            "mean_abs_move_bps": round(
                float(np.mean([abs(o.realised_bps) for o in self._outcomes])), 3
            ),
        }

    def series(self, limit: int = 300) -> list[dict[str, Any]]:
        """Recent outcomes for a drift chart (rolling log-loss is computed client-side)."""
        out = list(self._outcomes)[-limit:]
        return [
            {
                "ts_ms": o.ts_ms,
                "p_up": round(o.p[2], 4),
                "p_down": round(o.p[0], 4),
                "predicted": o.predicted,
                "realised": o.realised,
                "hit": o.predicted == o.realised,
                "log_loss": round(-math.log(max(o.p[o.realised], 1e-6)), 4),
                "realised_bps": round(o.realised_bps, 3),
            }
            for o in out
        ]
