"""
Explainability
==============

SHAP for the **served** model. The served model is an ensemble: one tree
model per calibration split, each followed by its own probability
calibrator. Calibration is a per-class monotone map, which SHAP cannot
attribute, so the explanation is of the tree models' **raw log-odds** for
the class the served (calibrated) model predicts, averaged over the tree
models — the quantity every calibrator starts from. The payload says so.

One `TreeExplainer` per tree model, each ~0.6 s to build, so the engine
builds them one at a time on its inference thread (a prediction waits behind
at most one build) when a model is installed, never on the event loop.
Explanations are computed on request (a single row).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from algoviz.ml.labels import CLASS_NAMES

logger = logging.getLogger("algoviz.ml.explain")


class Explainer:
    def __init__(self, model: Any, base_models: list[Any], feature_names: tuple[str, ...]) -> None:
        self._model = model
        self._bases = base_models
        self._names = feature_names
        self._explainers: list[Any] = [None] * len(base_models)
        self.available = True

    @property
    def size(self) -> int:
        return len(self._bases)

    def _get(self, i: int) -> Any:
        if self._explainers[i] is None:
            import shap

            self._explainers[i] = shap.TreeExplainer(self._bases[i])
        return self._explainers[i]

    def warm(self, i: int) -> None:
        try:
            self._get(i)
        except Exception:
            logger.exception("shap explainer build failed")
            self.available = False

    def _class_values(self, i: int, X: np.ndarray, cls: int) -> tuple[np.ndarray, float] | None:
        """One tree model's SHAP values and base value for `cls`; None if it never saw the class."""
        classes = [int(c) for c in self._bases[i].classes_]
        if cls not in classes:
            return None
        j = classes.index(cls)
        ex = self._get(i)
        values = ex.shap_values(X)
        ev = ex.expected_value
        # shap ≥ 0.45 returns (n, features, classes); older versions a list per class
        if isinstance(values, list):
            return np.asarray(values[j][0]), float(ev[j])
        arr = np.asarray(values)
        if arr.ndim == 3:
            return arr[0, :, j], float(ev[j])
        return arr[0], float(ev if np.ndim(ev) == 0 else ev[0])  # binary: one margin

    def explain(self, x: np.ndarray, top: int = 10) -> dict[str, Any] | None:
        try:
            X = x.reshape(1, -1)
            proba = self._model.predict_proba(X)[0]
            classes = [int(c) for c in self._model.classes_]
            local = int(np.argmax(proba))
            cls = classes[local]
            parts = [
                v for i in range(self.size) if (v := self._class_values(i, X, cls)) is not None
            ]
            if not parts:
                return None
            sv = np.mean([p[0] for p in parts], axis=0)
            base = float(np.mean([p[1] for p in parts]))
            order = np.argsort(np.abs(sv))[::-1][:top]
            return {
                "predicted_class": CLASS_NAMES[cls],
                "probability": round(float(proba[local]), 4),
                "models_averaged": len(parts),
                "base_value": round(base, 5),
                "prediction_logit": round(base + float(sv.sum()), 5),
                "contributions": [
                    {
                        "feature": self._names[i],
                        "value": round(float(x[i]), 5),
                        "shap": round(float(sv[i]), 5),
                    }
                    for i in order
                ],
            }
        except Exception:
            logger.exception("shap explanation failed")
            self.available = False
            return None
