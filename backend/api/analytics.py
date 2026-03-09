"""
AlgoViz Backend — Analytics API Routes
========================================

ML predictions, insights, rule engine, and analytics endpoints.
"""

from fastapi import APIRouter, Depends
from typing import Optional, List, Dict
from datetime import datetime

from services.market_data import market_service
from services.ml_engine import ml_engine
from config import settings

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ═════════════════════════════════════════════════════════════════════
# RULE ENGINE (migrated from src/decision/)
# ═════════════════════════════════════════════════════════════════════

# Rule definitions
RULES = {
    1: {
        "condition": lambda f: f.get("spread_bps", 0) > settings.SPREAD_HIGH_BPS,
        "priority": "HIGH",
        "insight": "Spread widened to {spread_bps:.1f} bps — liquidity deteriorating",
        "action": "Pause market orders; use limit orders only",
        "overcome": "Set limit orders at mid-price; accept partial fills",
        "impact": "Save 6-8 bps per trade",
    },
    2: {
        "condition": lambda f: f.get("spread_bps", 99) < settings.SPREAD_LOW_BPS,
        "priority": "LOW",
        "insight": "Excellent liquidity — spread at {spread_bps:.1f} bps",
        "action": "Optimal execution window — proceed with orders",
        "overcome": "Prioritize larger orders now",
        "impact": "Best execution quality",
    },
    3: {
        "condition": lambda f: f.get("imbalance", 0) < settings.IMBALANCE_STRONG_SELL,
        "priority": "HIGH",
        "insight": "Strong sell pressure at {imbalance_pct:.1f}%",
        "action": "Tighten stop-loss if long; delay buys",
        "overcome": "Set alerts for imbalance reversal",
        "impact": "Avoid 0.1-0.3% drawdown",
    },
    4: {
        "condition": lambda f: f.get("imbalance", 0) > settings.IMBALANCE_STRONG_BUY,
        "priority": "MEDIUM",
        "insight": "Buy-side demand at {imbalance_pct:.1f}%",
        "action": "Prices supported; delay sells",
        "overcome": "Wait for imbalance weakening",
        "impact": "Improve sell price 0.05%",
    },
    5: {
        "condition": lambda f: f.get("volatility_bps", 0) > settings.VOLATILITY_HIGH_BPS,
        "priority": "HIGH",
        "insight": "High volatility at {volatility_bps:.1f} bps",
        "action": "Reduce position size by 50%",
        "overcome": "Scale down; wait for mean-reversion",
        "impact": "Reduce drawdown 40%",
    },
    6: {
        "condition": lambda f: f.get("volatility_bps", 99) < settings.VOLATILITY_LOW_BPS,
        "priority": "LOW",
        "insight": "Low volatility — range-bound",
        "action": "Good for mean-reversion strategies",
        "overcome": "Tighter targets; frequent small trades",
        "impact": "Increase trade frequency",
    },
    7: {
        "condition": lambda f: f.get("velocity", 0) > settings.VELOCITY_SPIKE_MULTIPLIER * f.get("velocity_baseline", 20),
        "priority": "HIGH",
        "insight": "Velocity spike: {velocity:.1f}/s vs {velocity_baseline:.1f}/s baseline",
        "action": "Prepare for volatility; increase monitoring",
        "overcome": "Check news; tighten risk parameters",
        "impact": "10-30 second early warning",
    },
    8: {
        "condition": lambda f: f.get("velocity", 99) < settings.VELOCITY_THIN_MULTIPLIER * f.get("velocity_baseline", 20),
        "priority": "MEDIUM",
        "insight": "Thin market: {velocity:.1f}/s activity",
        "action": "Expect slippage; reduce order sizes",
        "overcome": "Split large orders into chunks",
        "impact": "Reduce market impact 50%",
    },
    9: {
        "condition": lambda f: f.get("price_vs_vwap", 0) > settings.PRICE_OVERBOUGHT_PCT,
        "priority": "MEDIUM",
        "insight": "Price {price_vs_vwap:.2f}% above VWAP — overbought",
        "action": "Wait for pullback if buying",
        "overcome": "Set limit orders at VWAP level",
        "impact": "Reduce slippage 3-5 bps",
    },
    10: {
        "condition": lambda f: f.get("price_vs_vwap", 0) < settings.PRICE_OVERSOLD_PCT,
        "priority": "MEDIUM",
        "insight": "Price {price_vs_vwap:.2f}% below VWAP — value zone",
        "action": "Favorable entry vs average",
        "overcome": "Use window for cost-averaging",
        "impact": "Improve entry 0.05-0.1%",
    },
}

PRIORITY_EMOJIS = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}


def evaluate_rules(features_dict: dict) -> List[dict]:
    """Evaluate all trading rules and return triggered insights."""
    triggered = []
    for rule_id, rule in RULES.items():
        try:
            if rule["condition"](features_dict):
                triggered.append({
                    "rule_id": rule_id,
                    "priority": rule["priority"],
                    "priority_emoji": PRIORITY_EMOJIS.get(rule["priority"], "⚪"),
                    "insight": rule["insight"].format(**features_dict),
                    "action": rule["action"],
                    "how_to_overcome": rule["overcome"],
                    "expected_impact": rule["impact"],
                    "triggered_at": datetime.utcnow().isoformat(),
                })
        except Exception:
            pass

    # Sort by priority
    order = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}
    triggered.sort(key=lambda x: order.get(x["priority"], 99))
    return triggered[:5]  # Top 5 insights


# ═════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═════════════════════════════════════════════════════════════════════

@router.get("/insights")
async def get_insights():
    """Get current trading insights from rule engine."""
    features = market_service.get_features()
    return evaluate_rules(features.to_dict())


@router.get("/prediction")
async def get_prediction():
    """Get current ML prediction from trained ensemble model."""
    return ml_engine.predict()


@router.get("/shap")
async def get_shap():
    """Get SHAP-based feature importance explanation for latest prediction."""
    return ml_engine.get_shap_explanation()


@router.get("/model-info")
async def get_model_info():
    """Get ML model status, training metrics, and configuration."""
    return ml_engine.get_model_info()


@router.get("/summary")
async def get_summary():
    """Get market summary with features, insights, prediction, and stats."""
    features = market_service.get_features()
    features_dict = features.to_dict()
    insights = evaluate_rules(features_dict)
    prediction = ml_engine.predict()
    stats = market_service.get_stats()

    return {
        "features": features_dict,
        "insights": insights,
        "prediction": prediction,
        "stats": stats,
        "timestamp": datetime.utcnow().isoformat(),
    }
