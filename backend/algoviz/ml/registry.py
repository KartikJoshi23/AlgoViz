"""
Model registry
==============

Artefacts on disk (`ML_MODEL_DIR/<symbol>/v<N>.joblib`, last K kept) plus a
row per version in `ml_models` with the walk-forward metrics, feature list
and hyper-parameters, so model lineage survives restarts and is browsable
from the UI.

Every artefact carries a **manifest**: the feature-schema hash, the lookback,
the label horizon and barrier parameters and the class order. On load it must
equal the running configuration's manifest; a model trained on other
features or another label definition is refused (and retrained) rather than
served against inputs it was never fitted on.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algoviz.core.time import ensure_aware
from algoviz.ml.features import FEATURE_SCHEMA, LOOKBACK, N_FEATURES
from algoviz.ml.labels import CLASS_NAMES
from algoviz.ml.train import FoldMetrics, TrainResult
from algoviz.models import MLModel

logger = logging.getLogger("algoviz.ml.registry")


def model_manifest(
    horizon_s: int, horizon_bars: int, barrier_k: float, min_barrier_bps: float
) -> dict[str, Any]:
    """What a model's inputs and labels were; two models are interchangeable only if these match."""
    return {
        "feature_schema": FEATURE_SCHEMA,
        "n_features": N_FEATURES,
        "lookback_bars": LOOKBACK,
        "label": "triple_barrier",
        "horizon_s": horizon_s,
        "horizon_bars": horizon_bars,
        "barrier_k": barrier_k,
        "min_barrier_bps": min_barrier_bps,
        "classes": list(CLASS_NAMES),
    }


class ModelRegistry:
    def __init__(self, base_dir: Path, symbol: str, *, keep: int = 5) -> None:
        self.dir = (
            Path(base_dir) / symbol.upper()
        ).resolve()  # absolute: rows match however the dir was given
        self.dir.mkdir(parents=True, exist_ok=True)
        self.symbol = symbol.upper()
        self.keep = keep

    # ── Artefacts (sync; call via to_thread) ──────────────────────

    def path(self, version: int) -> Path:
        return self.dir / f"v{version}.joblib"

    def save(self, result: TrainResult, version: int) -> Path:
        p = self.path(version)
        joblib.dump(
            {
                "version": version,
                "symbol": self.symbol,
                "manifest": result.manifest,
                "model": result.model,
                "base_models": result.base_models,
                "feature_names": list(result.feature_names),
                "n_samples": result.n_samples,
                "horizon_s": result.horizon_s,
                "trained_at": result.trained_at.isoformat(),
                "folds": [f.as_dict() for f in result.folds],
                "importance": result.importance,
                "importance_std": result.importance_std,
                "class_prior": result.class_prior,
                "calibration": result.calibration,
                "hyperparameters": result.hyperparameters,
            },
            p,
            compress=3,
        )
        self._gc()
        return p

    def _gc(self) -> None:
        files = sorted(self.dir.glob("v*.joblib"), key=lambda f: int(f.stem[1:]))
        for f in files[: -self.keep]:
            try:
                f.unlink()
            except OSError:
                pass

    def load_latest(self, manifest: dict[str, Any]) -> tuple[int, TrainResult | None]:
        """
        The newest artefact's version and, when its manifest matches `manifest`,
        the model. A refused or unreadable artefact still reports its version,
        so the next model is numbered after it rather than overwriting it.
        """
        files = sorted(self.dir.glob("v*.joblib"), key=lambda f: int(f.stem[1:]))
        if not files:
            return 0, None
        p = files[-1]
        version = int(p.stem[1:])
        try:
            d = joblib.load(p)
        except Exception:
            logger.warning("could not load %s", p, exc_info=True)
            return version, None
        found = d.get("manifest") or {}
        if found != manifest:
            changed = sorted(
                k for k in manifest.keys() | found.keys() if found.get(k) != manifest.get(k)
            )
            logger.warning(
                "%s v%d was trained for another configuration (%s); not serving it",
                self.symbol,
                version,
                f"{', '.join(changed)} differ" if found else "it predates manifests",
            )
            return version, None
        trained_at = ensure_aware(datetime.fromisoformat(d["trained_at"]))
        assert trained_at is not None
        result = TrainResult(
            model=d["model"],
            base_models=list(d["base_models"]),
            feature_names=tuple(d["feature_names"]),
            n_samples=int(d["n_samples"]),
            horizon_s=int(d["horizon_s"]),
            trained_at=trained_at,
            folds=[FoldMetrics.from_dict(f) for f in d.get("folds", [])],
            importance=dict(d.get("importance", {})),
            importance_std=dict(d.get("importance_std", {})),
            class_prior=dict(d.get("class_prior", {})),
            calibration=str(d.get("calibration", "none")),
            hyperparameters=dict(d.get("hyperparameters", {})),
            manifest=found,
        )
        return version, result

    # ── Database rows (async) ─────────────────────────────────────

    async def record(
        self, sf: async_sessionmaker[AsyncSession], result: TrainResult, version: int, path: Path
    ) -> int | None:
        try:
            async with sf() as session:
                await session.execute(
                    update(MLModel)
                    .where(MLModel.symbol == self.symbol, MLModel.is_active.is_(True))
                    .values(is_active=False)
                )
                row = MLModel(
                    symbol=self.symbol,
                    name=f"{self.symbol.lower()}-hgb-calibrated",
                    model_type="hist_gradient_boosting",
                    version=version,
                    file_path=str(path),
                    training_samples=result.n_samples,
                    horizon_s=result.horizon_s,
                    metrics=result.metrics_payload() | {"class_prior": result.class_prior},
                    feature_names=list(result.feature_names),
                    feature_importance=result.importance,
                    hyperparameters=result.hyperparameters
                    | {"calibration": result.calibration, "manifest": result.manifest},
                    is_active=True,
                    trained_at=result.trained_at,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return int(row.id)
        except Exception:
            logger.exception("registry row write failed")
            return None

    async def find_id(self, sf: async_sessionmaker[AsyncSession], path: Path) -> int | None:
        """The registry row of an artefact on disk (by path: versions repeat across data sources)."""
        try:
            async with sf() as session:
                row_id = await session.scalar(
                    select(MLModel.id)
                    .where(MLModel.symbol == self.symbol, MLModel.file_path == str(path))
                    .order_by(MLModel.id.desc())
                    .limit(1)
                )
            return int(row_id) if row_id is not None else None
        except Exception:
            logger.exception("registry row lookup failed")
            return None

    async def history(
        self, sf: async_sessionmaker[AsyncSession], limit: int = 20, before: int | None = None
    ) -> list[dict[str, Any]]:
        q = (
            select(MLModel)
            .where(MLModel.symbol == self.symbol)
            .order_by(MLModel.id.desc())  # newest first; versions repeat across data sources
            .limit(limit)
        )
        if before is not None:
            q = q.where(MLModel.id < before)
        async with sf() as session:
            rows = (await session.execute(q)).scalars().all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "name": r.name,
                "model_type": r.model_type,
                "version": r.version,
                "training_samples": r.training_samples,
                "horizon_s": r.horizon_s,
                "metrics": r.metrics,
                "feature_importance": r.feature_importance,
                "hyperparameters": r.hyperparameters,
                "is_active": r.is_active,
                "trained_at": r.trained_at.isoformat(),
            }
            for r in rows
        ]
