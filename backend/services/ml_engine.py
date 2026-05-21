"""
AlgoViz Backend — Real ML Engine
===================================

Production ML pipeline with scikit-learn for market prediction.

Features:
- Feature engineering pipeline (rolling stats, momentum, pattern detection)
- Ensemble model (RandomForest + GradientBoosting)
- Online learning with periodic retraining
- SHAP-based model explainability
- Model persistence and versioning
"""

import logging
import time
import math
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import joblib

from config import settings

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════
# FEATURE PIPELINE
# ═════════════════════════════════════════════════════════════════════

class MLFeaturePipeline:
    """
    Transforms raw market features into ML-ready feature vectors.
    
    Generates 25+ engineered features from base market data:
    - Price momentum (short/medium/long windows)
    - Volatility regime indicators
    - Order book pressure signals
    - VWAP/TWAP deviation metrics
    - Rolling statistical moments
    """

    FEATURE_NAMES = [
        # Price Momentum
        "price_return_5",      # 5-tick price return
        "price_return_10",     # 10-tick return
        "price_return_20",     # 20-tick return
        "price_acceleration",  # 2nd derivative of price
        
        # Spread & Liquidity
        "spread_bps",
        "spread_z_score",      # Z-score of spread vs rolling window
        "spread_expanding",    # Is spread widening?
        
        # Volume & Velocity
        "velocity",
        "velocity_ratio",      # velocity / baseline
        "velocity_acceleration",
        
        # Order Book
        "imbalance",
        "imbalance_momentum",  # Change in imbalance
        "buy_pressure",
        "buy_pressure_delta",  # Change in buy pressure
        
        # Volatility
        "volatility_bps",
        "volatility_ratio",    # Current / rolling avg
        "volatility_regime",   # 0=low, 1=medium, 2=high
        
        # VWAP/TWAP
        "price_vs_vwap",
        "price_vs_twap",
        "vwap_twap_spread",    # VWAP - TWAP divergence
        
        # Rolling Stats
        "price_rolling_mean_ratio",  # Price / rolling_mean
        "price_rolling_std",
        "return_skewness",
        "return_kurtosis",
        
        # Pattern Features
        "consecutive_ups",     # Consecutive up ticks
        "consecutive_downs",   # Consecutive down ticks
    ]

    def __init__(self, lookback: int = 50):
        self.lookback = lookback
        self._history: deque = deque(maxlen=500)
        self._scaler = StandardScaler()
        self._scaler_fitted = False

    def add_snapshot(self, features_dict: dict):
        """Add a market features snapshot to history."""
        self._history.append({
            "price": features_dict.get("current_price", 0),
            "spread_bps": features_dict.get("spread_bps", 0),
            "velocity": features_dict.get("velocity", 0),
            "velocity_baseline": features_dict.get("velocity_baseline", 20),
            "imbalance": features_dict.get("imbalance", 0),
            "buy_pressure": features_dict.get("buy_pressure", 0.5),
            "volatility_bps": features_dict.get("volatility_bps", 0),
            "price_vs_vwap": features_dict.get("price_vs_vwap", 0),
            "price_vs_twap": features_dict.get("price_vs_twap", 0),
            "vwap": features_dict.get("vwap", 0),
            "twap": features_dict.get("twap", 0),
            "timestamp": features_dict.get("timestamp", datetime.utcnow().isoformat()),
        })

    def extract_features(self) -> Optional[np.ndarray]:
        """
        Extract an ML feature vector from the accumulated history.
        Returns None if insufficient data.
        """
        if len(self._history) < max(self.lookback, 25):
            return None

        h = list(self._history)
        prices = [s["price"] for s in h if s["price"] > 0]
        if len(prices) < 25:
            return None

        latest = h[-1]

        # ── Price Momentum ──
        returns = self._calc_returns(prices)
        price_return_5 = self._period_return(prices, 5)
        price_return_10 = self._period_return(prices, 10)
        price_return_20 = self._period_return(prices, 20)
        price_acceleration = price_return_5 - self._period_return(prices, 5, offset=5) if len(prices) > 15 else 0

        # ── Spread ──
        spreads = [s["spread_bps"] for s in h[-self.lookback:]]
        spread_mean = np.mean(spreads) if spreads else 1.0
        spread_std = np.std(spreads) if len(spreads) > 1 else 1.0
        spread_z = (latest["spread_bps"] - spread_mean) / max(spread_std, 0.001)
        spread_expanding = 1.0 if len(spreads) > 5 and latest["spread_bps"] > np.mean(spreads[-5:]) else 0.0

        # ── Velocity ──
        velocities = [s["velocity"] for s in h[-self.lookback:]]
        vel_baseline = latest["velocity_baseline"] or 20.0
        vel_ratio = latest["velocity"] / max(vel_baseline, 1.0)
        vel_accel = (latest["velocity"] - (velocities[-5] if len(velocities) > 5 else latest["velocity"])) if velocities else 0

        # ── Order Book ──
        imbalances = [s["imbalance"] for s in h[-10:]]
        imb_momentum = (imbalances[-1] - imbalances[0]) if len(imbalances) > 1 else 0
        pressures = [s["buy_pressure"] for s in h[-10:]]
        bp_delta = (pressures[-1] - pressures[0]) if len(pressures) > 1 else 0

        # ── Volatility ──
        vols = [s["volatility_bps"] for s in h[-self.lookback:]]
        vol_mean = np.mean(vols) if vols else 1.0
        vol_ratio = latest["volatility_bps"] / max(vol_mean, 0.001)
        vol_regime = 2.0 if latest["volatility_bps"] > 20 else (1.0 if latest["volatility_bps"] > 10 else 0.0)

        # ── VWAP/TWAP ──
        vwap_twap_spread = 0.0
        if latest["vwap"] > 0 and latest["twap"] > 0:
            vwap_twap_spread = ((latest["vwap"] - latest["twap"]) / latest["vwap"]) * 10000

        # ── Rolling Stats ──
        recent_prices = prices[-self.lookback:]
        rolling_mean = np.mean(recent_prices)
        rolling_std = np.std(recent_prices) if len(recent_prices) > 1 else 0
        price_mean_ratio = prices[-1] / max(rolling_mean, 1) if rolling_mean else 1

        recent_returns = returns[-self.lookback:] if len(returns) >= self.lookback else returns
        skew = float(self._skewness(recent_returns)) if len(recent_returns) > 3 else 0
        kurt = float(self._kurtosis(recent_returns)) if len(recent_returns) > 3 else 0

        # ── Pattern Features ──
        consec_ups, consec_downs = self._consecutive_ticks(prices[-20:])

        feature_vector = np.array([
            price_return_5, price_return_10, price_return_20, price_acceleration,
            latest["spread_bps"], spread_z, spread_expanding,
            latest["velocity"], vel_ratio, vel_accel,
            latest["imbalance"], imb_momentum, latest["buy_pressure"], bp_delta,
            latest["volatility_bps"], vol_ratio, vol_regime,
            latest["price_vs_vwap"], latest.get("price_vs_twap", 0), vwap_twap_spread,
            price_mean_ratio, rolling_std, skew, kurt,
            float(consec_ups), float(consec_downs),
        ], dtype=np.float64)

        # Replace infinities and NaNs
        feature_vector = np.nan_to_num(feature_vector, nan=0.0, posinf=0.0, neginf=0.0)
        return feature_vector

    def get_feature_names(self) -> List[str]:
        return self.FEATURE_NAMES

    # ── Helpers ──

    @staticmethod
    def _calc_returns(prices: list) -> list:
        if len(prices) < 2:
            return []
        return [(prices[i] - prices[i-1]) / prices[i-1] * 10000 for i in range(1, len(prices))]

    @staticmethod
    def _period_return(prices: list, period: int, offset: int = 0) -> float:
        idx = len(prices) - 1 - offset
        if idx < period:
            return 0.0
        old = prices[idx - period]
        if old == 0:
            return 0.0
        return (prices[idx] - old) / old * 10000  # in bps

    @staticmethod
    def _skewness(data: list) -> float:
        if len(data) < 3:
            return 0.0
        arr = np.array(data)
        m = np.mean(arr)
        s = np.std(arr)
        if s == 0:
            return 0.0
        return float(np.mean(((arr - m) / s) ** 3))

    @staticmethod
    def _kurtosis(data: list) -> float:
        if len(data) < 4:
            return 0.0
        arr = np.array(data)
        m = np.mean(arr)
        s = np.std(arr)
        if s == 0:
            return 0.0
        return float(np.mean(((arr - m) / s) ** 4) - 3)

    @staticmethod
    def _consecutive_ticks(prices: list) -> Tuple[int, int]:
        ups = downs = 0
        for i in range(len(prices) - 1, 0, -1):
            if prices[i] > prices[i-1]:
                if downs > 0:
                    break
                ups += 1
            elif prices[i] < prices[i-1]:
                if ups > 0:
                    break
                downs += 1
            else:
                break
        return ups, downs


# ═════════════════════════════════════════════════════════════════════
# LABELS & TRAINING DATA
# ═════════════════════════════════════════════════════════════════════

@dataclass
class TrainingDataBuffer:
    """Accumulates labeled samples for model training."""
    
    X: List[np.ndarray] = field(default_factory=list)
    y: List[int] = field(default_factory=list)
    max_samples: int = 5000
    
    # Label lookahead: classify based on price move N ticks ahead
    lookahead_ticks: int = 10
    # Threshold for "significant" move (in bps)
    move_threshold_bps: float = 3.0

    def add_sample(self, features: np.ndarray, future_price: float, current_price: float):
        """Add a labeled sample. Label is UP(2), NEUTRAL(1), DOWN(0)."""
        if current_price <= 0:
            return
        move_bps = (future_price - current_price) / current_price * 10000
        if move_bps > self.move_threshold_bps:
            label = 2  # UP
        elif move_bps < -self.move_threshold_bps:
            label = 0  # DOWN
        else:
            label = 1  # NEUTRAL

        self.X.append(features)
        self.y.append(label)

        # Trim oldest samples
        if len(self.X) > self.max_samples:
            self.X = self.X[-self.max_samples:]
            self.y = self.y[-self.max_samples:]

    @property
    def size(self) -> int:
        return len(self.X)

    def get_arrays(self) -> Tuple[np.ndarray, np.ndarray]:
        return np.array(self.X), np.array(self.y)


# ═════════════════════════════════════════════════════════════════════
# ML ENGINE
# ═════════════════════════════════════════════════════════════════════

class MLEngine:
    """
    Production ML engine with:
    - Feature pipeline (26 engineered features)
    - Ensemble classifier (RandomForest + GradientBoosting)
    - Online data accumulation with periodic retraining
    - SHAP-based explainability
    - Model persistence
    """

    def __init__(self):
        self.pipeline = MLFeaturePipeline(lookback=50)
        self.training_buffer = TrainingDataBuffer()
        self.scaler = StandardScaler()

        # ── Models ──
        self.rf_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            min_samples_split=10,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        self.gb_model = GradientBoostingClassifier(
            n_estimators=80,
            max_depth=5,
            learning_rate=0.1,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
        )

        # ── State ──
        self._model_trained = False
        self._scaler_fitted = False
        self._training_count = 0
        self._last_train_time: Optional[datetime] = None
        self._model_metrics: Dict[str, float] = {}
        self._feature_importance: Dict[str, float] = {}

        # ── Pending labels (for delayed labeling) ──
        self._pending: deque = deque(maxlen=1000)

        # ── Model directory ──
        self._model_dir = Path(settings.ML_MODEL_DIR)
        self._model_dir.mkdir(parents=True, exist_ok=True)

        # Try loading existing models
        self._load_models()

    # ── Data Ingestion ────────────────────────────────────────────

    def ingest(self, features_dict: dict):
        """
        Ingest a market features snapshot.
        - Adds to feature pipeline history
        - Labels previous pending samples if enough time has passed
        - Triggers retraining if enough new data has accumulated
        """
        self.pipeline.add_snapshot(features_dict)
        price = features_dict.get("current_price", 0)

        # Try to label old pending entries
        self._resolve_pending(price)

        # Create new pending entry
        feature_vector = self.pipeline.extract_features()
        if feature_vector is not None and price > 0:
            self._pending.append({
                "features": feature_vector,
                "price": price,
                "tick_count": 0,
            })

        # Check if retraining is needed (run in background thread to avoid blocking event loop)
        if self.training_buffer.size >= settings.ML_MIN_DATA_POINTS and not self._model_trained:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, self._train)
            except RuntimeError:
                self._train()
        elif self._model_trained and self.training_buffer.size >= self._training_count + 200:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, self._train)
            except RuntimeError:
                self._train()

    def _resolve_pending(self, current_price: float):
        """Label pending samples that have enough ticks elapsed."""
        resolved = []
        for entry in self._pending:
            entry["tick_count"] += 1
            if entry["tick_count"] >= self.training_buffer.lookahead_ticks:
                self.training_buffer.add_sample(
                    entry["features"], current_price, entry["price"]
                )
                resolved.append(entry)

        for r in resolved:
            try:
                self._pending.remove(r)
            except ValueError:
                pass

    # ── Prediction ────────────────────────────────────────────────

    def predict(self) -> Dict[str, Any]:
        """
        Generate a prediction from current market state.
        Returns prediction dict with direction, confidence, and explainability.
        """
        feature_vector = self.pipeline.extract_features()
        if feature_vector is None:
            return self._default_prediction("insufficient_data")

        if not self._model_trained:
            return self._heuristic_prediction(feature_vector)

        try:
            # Scale features
            X = self.scaler.transform(feature_vector.reshape(1, -1))

            # Ensemble prediction (weighted vote)
            rf_proba = self.rf_model.predict_proba(X)[0]
            gb_proba = self.gb_model.predict_proba(X)[0]

            # Weighted average (RF 40%, GB 60%)
            ensemble_proba = rf_proba * 0.4 + gb_proba * 0.6

            # Direction mapping: 0=DOWN, 1=NEUTRAL, 2=UP
            pred_class = int(np.argmax(ensemble_proba))
            confidence = float(np.max(ensemble_proba))

            direction_map = {0: "down", 1: "neutral", 2: "up"}
            direction = direction_map.get(pred_class, "neutral")

            # Strong signals
            if confidence > 0.7:
                direction = f"strong_{direction}" if direction != "neutral" else direction

            # Signal action
            if direction in ("up", "strong_up"):
                signal = "BUY"
            elif direction in ("down", "strong_down"):
                signal = "SELL"
            else:
                signal = "HOLD"

            # Predicted move (from probability spread)
            up_prob = ensemble_proba[2] if len(ensemble_proba) > 2 else 0
            down_prob = ensemble_proba[0] if len(ensemble_proba) > 0 else 0
            predicted_move_bps = (up_prob - down_prob) * 10  # rough bps estimate

            # Momentum score
            momentum = (up_prob - down_prob) * 100

            # Regime detection
            volatility_bps = feature_vector[14] if len(feature_vector) > 14 else 0
            velocity_ratio = feature_vector[8] if len(feature_vector) > 8 else 1
            if volatility_bps > 20 and velocity_ratio > 2:
                regime = "breakout"
            elif volatility_bps > 15:
                regime = "volatile"
            elif volatility_bps < 8:
                regime = "quiet"
            else:
                regime = "ranging"

            # Reversal probability
            reversal_prob = 1.0 - confidence

            return {
                "direction": direction,
                "confidence": round(confidence, 4),
                "predicted_move_bps": round(predicted_move_bps, 2),
                "momentum_score": round(momentum, 2),
                "momentum_label": "bullish" if momentum > 20 else ("bearish" if momentum < -20 else "neutral"),
                "regime": regime,
                "reversal_probability": round(reversal_prob, 4),
                "signal_action": signal,
                "probabilities": {
                    "up": round(float(ensemble_proba[2]) if len(ensemble_proba) > 2 else 0, 4),
                    "neutral": round(float(ensemble_proba[1]) if len(ensemble_proba) > 1 else 0, 4),
                    "down": round(float(ensemble_proba[0]), 4),
                },
                "feature_importance": self._feature_importance,
                "model_name": "ensemble_rf_gb",
                "model_version": self._training_count,
                "training_samples": self.training_buffer.size,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return self._heuristic_prediction(feature_vector)

    def _heuristic_prediction(self, fv: np.ndarray) -> Dict[str, Any]:
        """Fallback heuristic when model isn't trained yet."""
        # Use basic momentum features
        price_ret_5 = fv[0] if len(fv) > 0 else 0
        price_ret_10 = fv[1] if len(fv) > 1 else 0
        imbalance = fv[10] if len(fv) > 10 else 0
        buy_pressure = fv[12] if len(fv) > 12 else 0.5

        momentum = price_ret_5 * 0.4 + price_ret_10 * 0.3 + imbalance * 20 + (buy_pressure - 0.5) * 10

        if momentum > 5:
            direction, signal = "up", "BUY"
        elif momentum < -5:
            direction, signal = "down", "SELL"
        else:
            direction, signal = "neutral", "HOLD"

        return {
            "direction": direction,
            "confidence": round(min(abs(momentum) / 20, 0.95), 4),
            "predicted_move_bps": round(momentum * 0.3, 2),
            "momentum_score": round(momentum, 2),
            "momentum_label": "bullish" if momentum > 5 else ("bearish" if momentum < -5 else "neutral"),
            "regime": "ranging",
            "reversal_probability": 0.5,
            "signal_action": signal,
            "probabilities": {"up": 0.33, "neutral": 0.34, "down": 0.33},
            "feature_importance": {},
            "model_name": "heuristic_fallback",
            "model_version": 0,
            "training_samples": self.training_buffer.size,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _default_prediction(self, reason: str = "") -> Dict[str, Any]:
        return {
            "direction": "neutral",
            "confidence": 0.0,
            "predicted_move_bps": 0.0,
            "momentum_score": 0.0,
            "momentum_label": "neutral",
            "regime": "unknown",
            "reversal_probability": 0.5,
            "signal_action": "HOLD",
            "probabilities": {"up": 0.33, "neutral": 0.34, "down": 0.33},
            "feature_importance": {},
            "model_name": reason or "none",
            "model_version": 0,
            "training_samples": self.training_buffer.size,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── Training ──────────────────────────────────────────────────

    def _train(self):
        """Train the ensemble model on accumulated data."""
        try:
            X, y = self.training_buffer.get_arrays()
            if len(X) < settings.ML_MIN_DATA_POINTS:
                return

            # Check class distribution — need at least 2 classes
            unique_classes = np.unique(y)
            if len(unique_classes) < 2:
                logger.info(f"Skipping training: only {len(unique_classes)} class(es)")
                return

            logger.info(f"Training models on {len(X)} samples, {len(unique_classes)} classes")

            # Scale features
            self.scaler.fit(X)
            X_scaled = self.scaler.transform(X)
            self._scaler_fitted = True

            # Train RF
            self.rf_model.fit(X_scaled, y)

            # Train GB
            self.gb_model.fit(X_scaled, y)

            # Evaluate (cross-validation if enough data)
            if len(X) >= 50:
                rf_scores = cross_val_score(self.rf_model, X_scaled, y, cv=min(5, len(unique_classes)), scoring="f1_weighted")
                gb_scores = cross_val_score(self.gb_model, X_scaled, y, cv=min(5, len(unique_classes)), scoring="f1_weighted")
                
                self._model_metrics = {
                    "rf_f1_mean": round(float(np.mean(rf_scores)), 4),
                    "rf_f1_std": round(float(np.std(rf_scores)), 4),
                    "gb_f1_mean": round(float(np.mean(gb_scores)), 4),
                    "gb_f1_std": round(float(np.std(gb_scores)), 4),
                    "samples": len(X),
                    "classes": len(unique_classes),
                }
                logger.info(f"RF F1: {self._model_metrics['rf_f1_mean']:.3f} ± {self._model_metrics['rf_f1_std']:.3f}")
                logger.info(f"GB F1: {self._model_metrics['gb_f1_mean']:.3f} ± {self._model_metrics['gb_f1_std']:.3f}")

            # Feature importance (from RF)
            importances = self.rf_model.feature_importances_
            feature_names = self.pipeline.get_feature_names()
            self._feature_importance = {
                name: round(float(imp), 4)
                for name, imp in sorted(
                    zip(feature_names[:len(importances)], importances),
                    key=lambda x: x[1],
                    reverse=True,
                )[:10]  # Top 10 features
            }

            self._model_trained = True
            self._training_count += 1
            self._last_train_time = datetime.utcnow()

            # Save models
            self._save_models()

            logger.info(f"Model training complete (v{self._training_count})")

        except Exception as e:
            logger.error(f"Training error: {e}")

    # ── Persistence ───────────────────────────────────────────────

    def _save_models(self):
        """Save trained models to disk."""
        try:
            joblib.dump(self.rf_model, self._model_dir / "rf_model.joblib")
            joblib.dump(self.gb_model, self._model_dir / "gb_model.joblib")
            joblib.dump(self.scaler, self._model_dir / "scaler.joblib")
            joblib.dump({
                "training_count": self._training_count,
                "metrics": self._model_metrics,
                "importance": self._feature_importance,
                "trained_at": self._last_train_time.isoformat() if self._last_train_time else None,
            }, self._model_dir / "metadata.joblib")
            logger.info(f"Models saved to {self._model_dir}")
        except Exception as e:
            logger.error(f"Model save error: {e}")

    def _load_models(self):
        """Load previously trained models from disk."""
        try:
            rf_path = self._model_dir / "rf_model.joblib"
            gb_path = self._model_dir / "gb_model.joblib"
            scaler_path = self._model_dir / "scaler.joblib"
            meta_path = self._model_dir / "metadata.joblib"

            if all(p.exists() for p in [rf_path, gb_path, scaler_path]):
                self.rf_model = joblib.load(rf_path)
                self.gb_model = joblib.load(gb_path)
                self.scaler = joblib.load(scaler_path)
                self._scaler_fitted = True
                self._model_trained = True

                if meta_path.exists():
                    meta = joblib.load(meta_path)
                    self._training_count = meta.get("training_count", 1)
                    self._model_metrics = meta.get("metrics", {})
                    self._feature_importance = meta.get("importance", {})

                logger.info(f"Loaded existing models (v{self._training_count})")
        except Exception as e:
            logger.warning(f"Could not load models: {e}")

    # ── Public API ────────────────────────────────────────────────

    def get_model_info(self) -> Dict[str, Any]:
        """Get model status and metrics."""
        return {
            "model_trained": self._model_trained,
            "training_count": self._training_count,
            "training_samples": self.training_buffer.size,
            "pending_labels": len(self._pending),
            "metrics": self._model_metrics,
            "feature_importance": self._feature_importance,
            "last_trained": self._last_train_time.isoformat() if self._last_train_time else None,
            "feature_names": self.pipeline.get_feature_names(),
        }

    def get_shap_explanation(self) -> Optional[Dict[str, Any]]:
        """
        Get SHAP-based feature importance explanation.
        Returns top contributing features for the latest prediction.
        """
        if not self._model_trained:
            return None

        feature_vector = self.pipeline.extract_features()
        if feature_vector is None:
            return None

        try:
            import shap

            X_scaled = self.scaler.transform(feature_vector.reshape(1, -1))
            explainer = shap.TreeExplainer(self.rf_model)
            shap_values = explainer.shap_values(X_scaled)

            feature_names = self.pipeline.get_feature_names()

            # Get SHAP values for the predicted class
            pred_class = int(self.rf_model.predict(X_scaled)[0])
            
            if isinstance(shap_values, list):
                sv = shap_values[pred_class][0]
            else:
                sv = shap_values[0]

            explanation = {}
            for name, val in sorted(
                zip(feature_names[:len(sv)], sv),
                key=lambda x: abs(x[1]),
                reverse=True,
            )[:8]:  # Top 8
                explanation[name] = {
                    "shap_value": round(float(val), 6),
                    "direction": "↑" if val > 0 else "↓",
                    "magnitude": "strong" if abs(val) > 0.1 else ("moderate" if abs(val) > 0.05 else "weak"),
                }

            return {
                "predicted_class": ["DOWN", "NEUTRAL", "UP"][pred_class],
                "top_features": explanation,
                "base_value": round(float(explainer.expected_value[pred_class]) if isinstance(explainer.expected_value, list) else float(explainer.expected_value), 4),
            }

        except ImportError:
            logger.warning("SHAP not installed, skipping explainability")
            return None
        except Exception as e:
            logger.error(f"SHAP explanation error: {e}")
            return None


# ── Singleton ─────────────────────────────────────────────────────
ml_engine = MLEngine()
