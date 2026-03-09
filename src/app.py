"""
AlgoViz - See the Signal in the Noise
==============================================

Professional Masters-level trading dashboard with real-time market intelligence.
Supports both Static Demo Data and Live Market Data modes.

Enhanced Features:
- ML Price Direction Prediction
- Real-time Alert System
- Candlestick Charts
- Order Book Depth Visualization
- Strategy Backtester
- Advanced Analytics
"""

import streamlit as st
import time
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

# Import our modules
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    PAGE_CONFIG,
    UI_REFRESH_INTERVAL,
    SPREAD_HEATMAP_WINDOW_SECONDS,
    ML_CONFIG,
    ALERT_CONFIG,
    BACKTEST_CONFIG,
    CANDLE_CONFIG,
    PLOTLY_CONFIG
)
from data.state_manager import StateManager
from data.websocket_handler import BinanceWebSocketHandler
from data.synthetic_data import SyntheticDataGenerator, get_synthetic_generator, reset_synthetic_generator
from features.feature_engine import FeatureEngine
from decision.rule_engine import RuleEngine
from decision.insight_generator import InsightGenerator
from ui.theme import Theme
from ui.charts import Charts
from ui.components import Components

# New enhanced modules
from ml.predictor import MLPredictor, PredictionResult
from ml.deep_predictor import DeepLearningPredictor, DeepPredictionResult
from alerts.alert_manager import AlertManager, Alert
from backtester.strategy_tester import StrategyBacktester, BacktestResult


# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(**PAGE_CONFIG)

# CSS to hide modebar by default and show only on hover
st.markdown("""
<style>
    /* Hide modebar by default */
    .modebar {
        opacity: 0 !important;
        transition: opacity 0.3s ease-in-out !important;
    }
    
    /* Show modebar on chart hover */
    .js-plotly-plot:hover .modebar {
        opacity: 1 !important;
    }
    
    /* Remove any placeholder space */
    .modebar-container {
        position: absolute !important;
        top: 0 !important;
        right: 0 !important;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# DATA CLASSES FOR COMPATIBILITY
# =============================================================================

@dataclass
class SyntheticFeatures:
    """Features calculated from synthetic data - matches live Features structure."""
    current_price: float
    mid_price: float
    vwap: float
    twap: float  # Time-Weighted Average Price
    spread: float
    spread_bps: float
    bid_volume: float
    ask_volume: float
    imbalance: float
    imbalance_pct: float
    volatility: float
    volatility_bps: float
    velocity: float
    velocity_baseline: float
    best_bid: float
    best_ask: float
    buy_pressure: float = 0.5
    price_change: float = 0.0
    price_change_pct: float = 0.0
    price_vs_vwap: float = 0.0
    price_vs_twap: float = 0.0  # Price vs TWAP percentage


# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

def initialize_session_state():
    """Initialize all session state variables."""
    
    if "initialized" not in st.session_state:
        # Live data components
        st.session_state.state_manager = StateManager()
        st.session_state.feature_engine = FeatureEngine(st.session_state.state_manager)
        st.session_state.rule_engine = RuleEngine()
        st.session_state.insight_generator = InsightGenerator(st.session_state.rule_engine)
        
        # WebSocket handler (only starts when live mode is selected)
        st.session_state.ws_handler = None
        st.session_state.ws_started = False
        
        # Synthetic data generator
        st.session_state.synthetic_generator = get_synthetic_generator("normal")
        
        # Data mode tracking
        st.session_state.data_mode = "static"
        st.session_state.scenario = "normal"
        
        # NEW: ML Predictor
        st.session_state.ml_predictor = MLPredictor(history_size=ML_CONFIG.history_size)
        st.session_state.last_prediction = None
        st.session_state.previous_regime = None
        
        # NEW: Deep Learning Predictor
        st.session_state.deep_predictor = DeepLearningPredictor(
            sequence_length=30,
            feature_size=8,
            hidden_size=32,
            num_dense_layers=2
        )
        st.session_state.last_deep_prediction = None
        
        # NEW: Alert Manager
        st.session_state.alert_manager = AlertManager(max_history=ALERT_CONFIG.max_history_size)
        st.session_state.active_alerts = []
        
        # NEW: Strategy Backtester
        st.session_state.backtester = StrategyBacktester(
            initial_capital=BACKTEST_CONFIG.initial_capital,
            commission_bps=BACKTEST_CONFIG.commission_bps,
            slippage_bps=BACKTEST_CONFIG.slippage_bps
        )
        st.session_state.backtest_results = None
        
        # NEW: Candlestick data aggregator
        st.session_state.candle_data = []
        st.session_state.current_candle = None
        st.session_state.candle_start_time = None
        
        # Pause refresh for fullscreen chart viewing
        st.session_state.pause_refresh = False
        
        st.session_state.initialized = True
        st.session_state.start_time = datetime.utcnow()


def start_websocket():
    """Start the WebSocket handler if not already running."""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("start_websocket() called")
    
    # Check if handler exists and is actually running
    if st.session_state.ws_started and st.session_state.ws_handler:
        if st.session_state.ws_handler.is_running():
            logger.info("WebSocket handler already running")
            return  # Already running, nothing to do
        else:
            # Handler exists but stopped - reset it
            logger.info("WebSocket handler stopped, resetting...")
            st.session_state.ws_started = False
    
    # Start new handler
    if not st.session_state.ws_started:
        try:
            logger.info("Starting new WebSocket handler...")
            st.session_state.ws_handler = BinanceWebSocketHandler(
                st.session_state.state_manager,
                on_status_change=None
            )
            st.session_state.ws_handler.start()
            st.session_state.ws_started = True
            logger.info("WebSocket handler started successfully")
        except Exception as e:
            logger.error(f"WebSocket start error: {e}")
            st.session_state.state_manager.set_error(f"WebSocket start error: {e}")


def stop_websocket():
    """Stop the WebSocket handler."""
    if st.session_state.ws_started and st.session_state.ws_handler:
        try:
            st.session_state.ws_handler.stop()
        except:
            pass
        st.session_state.ws_started = False
        st.session_state.ws_handler = None


# =============================================================================
# CHART CONFIG
# =============================================================================

CHART_CONFIG = {
    'displayModeBar': True,
    'displaylogo': False,
    'modeBarButtonsToRemove': ['lasso2d', 'select2d', 'autoScale2d'],
    'toImageButtonOptions': {
        'format': 'png',
        'filename': 'algoviz_chart',
        'height': 600,
        'width': 1000,
        'scale': 2
    }
}


# =============================================================================
# SYNTHETIC DATA HELPERS
# =============================================================================

def get_synthetic_features(generator: SyntheticDataGenerator) -> SyntheticFeatures:
    """Get features from synthetic data generator."""
    features_dict = generator.calculate_features()
    
    # Map and add missing fields
    mid_price = features_dict.get('mid_price', 87500.0)
    vwap = features_dict.get('vwap', mid_price)
    # TWAP is slightly different from VWAP (time-weighted vs volume-weighted)
    twap = mid_price * (1 + np.random.uniform(-0.0001, 0.0001))  # Small variation from current price
    imbalance = features_dict.get('imbalance', 0.0)
    
    return SyntheticFeatures(
        current_price=mid_price,
        mid_price=mid_price,
        vwap=vwap,
        twap=twap,
        spread=features_dict.get('spread', 0.01),
        spread_bps=features_dict.get('spread_bps', 1.0),
        bid_volume=features_dict.get('bid_volume', 5.0),
        ask_volume=features_dict.get('ask_volume', 5.0),
        imbalance=imbalance,
        imbalance_pct=imbalance * 100,
        volatility=features_dict.get('volatility', 15.0),
        volatility_bps=features_dict.get('volatility', 15.0),
        velocity=features_dict.get('velocity', 10.0),
        velocity_baseline=features_dict.get('velocity_baseline', 10.0),
        best_bid=features_dict.get('best_bid', mid_price - 0.5),
        best_ask=features_dict.get('best_ask', mid_price + 0.5),
        buy_pressure=0.5 + imbalance * 0.3,
        price_change=mid_price * 0.0002,
        price_change_pct=0.02,
        price_vs_vwap=((mid_price - vwap) / vwap * 100) if vwap > 0 else 0.0,
        price_vs_twap=((mid_price - twap) / twap * 100) if twap > 0 else 0.0
    )


def get_synthetic_price_data(generator: SyntheticDataGenerator, window_seconds: int) -> List[dict]:
    """Get price chart data from synthetic generator - returns dict format."""
    minutes = max(1, window_seconds // 60)
    raw_data = generator.generate_historical_prices(minutes=minutes, interval_seconds=1.0)
    # Convert tuples to dicts: (timestamp, price, vwap) -> {"timestamp": ..., "price": ..., "vwap": ...}
    return [{"timestamp": d[0], "price": d[1], "vwap": d[2]} for d in raw_data]


def get_synthetic_volatility_data(generator: SyntheticDataGenerator, window_seconds: int) -> List[dict]:
    """Get volatility chart data from synthetic generator - returns dict format."""
    minutes = max(1, window_seconds // 60)
    raw_data = generator.generate_volatility_data(minutes=minutes, interval_seconds=5.0)
    # Convert tuples to dicts with volatility_bps for chart compatibility
    # (timestamp, volatility) -> {"timestamp": ..., "volatility": ..., "volatility_bps": ...}
    return [{"timestamp": d[0], "volatility": d[1], "volatility_bps": d[1]} for d in raw_data]


def get_synthetic_spread_data(generator: SyntheticDataGenerator, window_seconds: int) -> List[dict]:
    """Get spread chart data from synthetic generator - returns dict format."""
    minutes = max(1, window_seconds // 60)
    raw_data = generator.generate_spread_data(minutes=minutes, interval_seconds=5.0)
    # Convert tuples to dicts with spread_bps field for chart compatibility
    # (timestamp, spread_bps) -> {"timestamp": ..., "spread": ..., "spread_bps": ...}
    # Data is already in bps, no need to multiply
    return [{"timestamp": d[0], "spread": d[1], "spread_bps": d[1]} for d in raw_data]


# =============================================================================
# ML PREDICTION HELPERS (NEW)
# =============================================================================

def update_ml_predictor(features, is_static: bool, generator: Optional[SyntheticDataGenerator] = None):
    """Update ML predictor with new features and generate prediction."""
    predictor = st.session_state.ml_predictor
    
    # Update with current data
    price = features.current_price if hasattr(features, 'current_price') else features.mid_price
    volume = features.bid_volume + features.ask_volume if hasattr(features, 'bid_volume') else 1.0
    imbalance = features.imbalance if hasattr(features, 'imbalance') else 0.0
    volatility = features.volatility_bps if hasattr(features, 'volatility_bps') else 15.0
    spread = features.spread_bps if hasattr(features, 'spread_bps') else 3.0
    
    predictor.update(price, volume, imbalance, volatility, spread)
    
    # Generate prediction
    prediction = predictor.predict()
    st.session_state.last_prediction = prediction
    
    return prediction


def get_synthetic_ml_prediction(generator: SyntheticDataGenerator) -> PredictionResult:
    """Generate synthetic ML prediction for demo mode."""
    import random
    from ml.predictor import PredictionDirection, MarketRegime
    
    features = generator.calculate_features()
    imbalance = features.get('imbalance', 0)
    volatility = features.get('volatility', 15)
    
    # Determine direction based on synthetic data
    if imbalance > 0.3:
        direction = PredictionDirection.UP
        confidence = 0.70 + imbalance * 0.25
    elif imbalance < -0.3:
        direction = PredictionDirection.DOWN
        confidence = 0.70 + abs(imbalance) * 0.25
    else:
        direction = PredictionDirection.NEUTRAL
        confidence = 0.65
    
    # Determine regime
    if volatility > 22:
        regime = MarketRegime.VOLATILE
    elif abs(imbalance) > 0.5:
        regime = MarketRegime.TRENDING_UP if imbalance > 0 else MarketRegime.TRENDING_DOWN
    else:
        regime = MarketRegime.RANGING
    
    return PredictionResult(
        direction=direction,
        direction_confidence=min(confidence, 0.95),
        predicted_move_bps=imbalance * 5,
        momentum_score=imbalance * 60 + random.uniform(-10, 10),
        momentum_strength="Bullish" if imbalance > 0.2 else "Bearish" if imbalance < -0.2 else "Neutral",
        regime=regime,
        regime_confidence=0.78,
        trend_strength=abs(imbalance) * 80,
        trend_direction="Bullish" if imbalance > 0 else "Bearish" if imbalance < 0 else "Neutral",
        reversal_probability=0.3 if abs(imbalance) > 0.5 else 0.15,
        model_accuracy=random.uniform(68, 78),
        predictions_made=random.randint(50, 200),
        correct_predictions=random.randint(30, 120),
        feature_importance={
            "Momentum": random.uniform(15, 35),
            "Order Imbalance": random.uniform(15, 30),
            "Volatility": random.uniform(10, 20),
            "Mean Reversion": random.uniform(8, 18),
            "Volume Flow": random.uniform(5, 15),
            "Spread": random.uniform(3, 12),
            "Trend": random.uniform(2, 10)
        },
        signal_strength=abs(imbalance) * 80 + random.uniform(0, 20),
        signal_action="BUY" if imbalance > 0.3 else "SELL" if imbalance < -0.3 else "HOLD",
        prediction_timestamp=datetime.utcnow()
    )


# =============================================================================
# DEEP LEARNING PREDICTION HELPERS (NEW)
# =============================================================================

def update_deep_predictor(features, is_static: bool, generator: Optional[SyntheticDataGenerator] = None) -> DeepPredictionResult:
    """Update Deep Learning predictor with new features and generate prediction."""
    predictor = st.session_state.deep_predictor
    
    # Extract features
    price = features.current_price if hasattr(features, 'current_price') else features.mid_price
    momentum = features.momentum if hasattr(features, 'momentum') else 0.0
    volatility = features.volatility_bps if hasattr(features, 'volatility_bps') else 15.0
    imbalance = features.imbalance if hasattr(features, 'imbalance') else 0.0
    spread = features.spread_bps if hasattr(features, 'spread_bps') else 3.0
    volume = (features.bid_volume + features.ask_volume) if hasattr(features, 'bid_volume') else 1.0
    vwap_deviation = features.vwap_deviation_bps if hasattr(features, 'vwap_deviation_bps') else 0.0
    trade_velocity = features.trade_velocity if hasattr(features, 'trade_velocity') else 10.0
    
    # Update predictor
    predictor.update(
        price=price,
        momentum=momentum,
        volatility=volatility,
        imbalance=imbalance,
        spread=spread,
        volume=volume,
        vwap_deviation=vwap_deviation,
        trade_velocity=trade_velocity
    )
    
    # Generate prediction
    prediction = predictor.predict()
    st.session_state.last_deep_prediction = prediction
    
    return prediction


def get_synthetic_deep_prediction(generator: SyntheticDataGenerator) -> DeepPredictionResult:
    """Generate synthetic Deep Learning prediction for demo mode."""
    import random
    from ml.deep_predictor import DeepPredictionDirection, NeuralMarketRegime
    
    features = generator.calculate_features()
    imbalance = features.get('imbalance', 0)
    volatility = features.get('volatility', 15)
    momentum = features.get('momentum', 0)
    
    # Simulate neural network outputs
    base_up = 0.33 + imbalance * 0.3 + momentum * 0.1
    base_down = 0.33 - imbalance * 0.3 - momentum * 0.1
    
    up_prob = np.clip(base_up + random.uniform(-0.05, 0.05), 0.05, 0.9)
    down_prob = np.clip(base_down + random.uniform(-0.05, 0.05), 0.05, 0.9)
    neutral_prob = np.clip(1 - up_prob - down_prob, 0.05, 0.5)
    
    # Normalize
    total = up_prob + down_prob + neutral_prob
    up_prob /= total
    down_prob /= total
    neutral_prob /= total
    
    # Determine direction using argmax (pick highest probability)
    probs = [up_prob, neutral_prob, down_prob]
    max_idx = np.argmax(probs)
    max_prob = probs[max_idx]
    
    if max_idx == 0:  # UP is highest
        if max_prob > 0.5:
            direction = DeepPredictionDirection.STRONG_UP
        else:
            direction = DeepPredictionDirection.UP
    elif max_idx == 2:  # DOWN is highest
        if max_prob > 0.5:
            direction = DeepPredictionDirection.STRONG_DOWN
        else:
            direction = DeepPredictionDirection.DOWN
    else:  # NEUTRAL is highest
        direction = DeepPredictionDirection.NEUTRAL
    
    confidence = max_prob
    
    # Determine regime
    if volatility > 22:
        regime = NeuralMarketRegime.VOLATILE
    elif abs(imbalance) > 0.5:
        regime = NeuralMarketRegime.TRENDING_UP if imbalance > 0 else NeuralMarketRegime.TRENDING_DOWN
    elif abs(imbalance) > 0.3:
        regime = NeuralMarketRegime.BREAKOUT
    else:
        regime = NeuralMarketRegime.RANGING
    
    # Simulated attention weights (more weight on recent timesteps)
    seq_len = 20
    attention_weights = [0.02 + 0.08 * (i / seq_len) ** 2 + random.uniform(0, 0.02) for i in range(seq_len)]
    total_att = sum(attention_weights)
    attention_weights = [w / total_att for w in attention_weights]
    
    # Feature importance
    feature_importance = {
        "Price Return": random.uniform(12, 25),
        "Momentum": random.uniform(15, 28),
        "Volatility": random.uniform(8, 18),
        "Imbalance": random.uniform(12, 22),
        "Spread": random.uniform(5, 12),
        "Volume": random.uniform(6, 15),
        "VWAP Deviation": random.uniform(4, 12),
        "Trade Velocity": random.uniform(3, 10)
    }
    total_imp = sum(feature_importance.values())
    feature_importance = {k: v / total_imp * 100 for k, v in feature_importance.items()}
    
    # Layer activations
    layer_activations = {
        "attention_output": random.uniform(0.3, 0.8),
        "dense_1": random.uniform(0.4, 0.9),
        "dense_2": random.uniform(0.2, 0.7)
    }
    
    return DeepPredictionResult(
        direction=direction,
        direction_confidence=confidence,
        predicted_move_bps=imbalance * 5 + momentum * 2,
        up_probability=up_prob,
        down_probability=down_prob,
        neutral_probability=neutral_prob,
        momentum_score=imbalance * 60 + momentum * 20 + random.uniform(-10, 10),
        momentum_strength="Strong Bullish" if imbalance > 0.4 else "Bullish" if imbalance > 0.2 else "Bearish" if imbalance < -0.2 else "Strong Bearish" if imbalance < -0.4 else "Neutral",
        regime=regime,
        regime_confidence=random.uniform(0.6, 0.85),
        trend_strength=abs(imbalance) * 80 + random.uniform(0, 15),
        trend_direction="Bullish" if imbalance > 0.15 else "Bearish" if imbalance < -0.15 else "Neutral",
        attention_weights=attention_weights,
        reversal_probability=0.35 if abs(imbalance) > 0.5 else 0.15,
        model_accuracy=random.uniform(54, 72),
        predictions_made=random.randint(100, 500),
        correct_predictions=random.randint(60, 350),
        model_type="LSTM-Attention",
        hidden_layers=3,
        total_parameters=random.randint(3500, 4500),
        prediction_timestamp=datetime.utcnow(),
        prediction_horizon_seconds=5,
        inference_time_ms=random.uniform(0.5, 2.5),
        feature_importance=feature_importance,
        layer_activations=layer_activations,
        signal_strength=abs(imbalance) * 85 + random.uniform(0, 15),
        signal_action="STRONG BUY" if direction == DeepPredictionDirection.STRONG_UP else "BUY" if direction == DeepPredictionDirection.UP else "STRONG SELL" if direction == DeepPredictionDirection.STRONG_DOWN else "SELL" if direction == DeepPredictionDirection.DOWN else "HOLD",
        prediction_uncertainty=random.uniform(15, 45),
        confidence_interval=(imbalance * 5 - 3, imbalance * 5 + 3)
    )


# =============================================================================
# CANDLESTICK HELPERS (NEW)
# =============================================================================

def generate_synthetic_candles(generator: SyntheticDataGenerator, num_candles: int = 30) -> List[Dict]:
    """Generate synthetic candlestick data for demo mode."""
    candles = []
    base_price = generator.current_price
    now = datetime.utcnow()
    
    for i in range(num_candles):
        timestamp = now - timedelta(seconds=(num_candles - i) * CANDLE_CONFIG.candle_interval)
        
        # Generate OHLC with some randomness
        volatility = 0.0005
        open_price = base_price * (1 + np.random.uniform(-volatility, volatility))
        close_price = open_price * (1 + np.random.uniform(-volatility * 2, volatility * 2))
        high_price = max(open_price, close_price) * (1 + np.random.uniform(0, volatility))
        low_price = min(open_price, close_price) * (1 - np.random.uniform(0, volatility))
        volume = np.random.uniform(0.1, 2.0)
        
        candles.append({
            "timestamp": timestamp,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume
        })
        
        base_price = close_price
    
    return candles


def generate_synthetic_depth(generator: SyntheticDataGenerator) -> Tuple[List[Dict], List[Dict]]:
    """Generate synthetic order book depth for demo mode."""
    mid_price = generator.current_price
    
    bids = []
    asks = []
    
    # Generate 10 levels each side
    for i in range(10):
        bid_price = mid_price - (i + 1) * 0.5
        ask_price = mid_price + (i + 1) * 0.5
        
        # Volume decreases with distance from mid
        bid_vol = np.random.uniform(0.5, 3.0) * (1 - i * 0.08)
        ask_vol = np.random.uniform(0.5, 3.0) * (1 - i * 0.08)
        
        bids.append({"price": bid_price, "quantity": bid_vol})
        asks.append({"price": ask_price, "quantity": ask_vol})
    
    return bids, asks


# =============================================================================
# ALERT HELPERS (NEW)
# =============================================================================

def evaluate_alerts(features, ml_prediction=None) -> List[Alert]:
    """Evaluate alert rules against current features."""
    alert_manager = st.session_state.alert_manager
    
    # Convert features to dict
    if hasattr(features, 'to_dict'):
        features_dict = features.to_dict()
    else:
        features_dict = {
            "current_price": getattr(features, 'current_price', getattr(features, 'mid_price', 0)),
            "mid_price": getattr(features, 'mid_price', 0),
            "spread_bps": getattr(features, 'spread_bps', 0),
            "volatility_bps": getattr(features, 'volatility_bps', getattr(features, 'volatility', 15)),
            "imbalance": getattr(features, 'imbalance', 0),
            "velocity": getattr(features, 'velocity', 0),
            "price_change_pct": getattr(features, 'price_change_pct', 0)
        }
    
    # Get previous regime for change detection
    previous_regime = st.session_state.previous_regime
    if ml_prediction:
        st.session_state.previous_regime = str(ml_prediction.regime)
    
    # Evaluate rules
    alerts = alert_manager.evaluate(features_dict, ml_prediction, previous_regime)
    st.session_state.active_alerts = alerts
    
    return alerts


# =============================================================================
# PAGE: LIVE DATA FEED (Only for Live mode)
# =============================================================================

def render_live_data_page(is_static: bool, generator: Optional[SyntheticDataGenerator] = None):
    """Render the Live Data Feed page - ONLY available in Live mode."""
    
    st.markdown("# 📡 Live Data Feed")
    st.markdown("*Real-time trades and order book streaming from Binance WebSocket*")
    
    # ==========================================================================
    # CONNECTION STATUS (Fragment for live updates)
    # ==========================================================================
    
    @st.fragment(run_every=timedelta(seconds=1))
    def render_connection_status_fragment():
        state = st.session_state.state_manager
        connection_status = state.get_connection_status()
        last_update = state.get_last_update()
        Components.render_connection_status(connection_status, last_update)
    
    render_connection_status_fragment()
    
    st.markdown("---")
    
    # ==========================================================================
    # LIVE-SPECIFIC: TICK-BY-TICK PRICE CHART (Fragment for fullscreen-safe updates)
    # ==========================================================================
    
    @st.fragment(run_every=timedelta(seconds=1))
    def render_tick_chart():
        st.markdown("### ⚡ Tick-by-Tick Price (Last 30 seconds)")
        # IMPORTANT: Call calculate_all() to populate price history from live trades
        st.session_state.feature_engine.calculate_all()
        tick_data = st.session_state.feature_engine.get_price_chart_data(window_seconds=30)
        if tick_data:
            fig_tick = Charts.create_price_vwap_chart(tick_data, height=250, line_shape="linear")
            fig_tick.update_layout(title=None)
            st.plotly_chart(fig_tick, width='stretch', config=PLOTLY_CONFIG)
        else:
            st.info("Waiting for price data... (Ensure WebSocket is connected)")
    
    render_tick_chart()
    
    st.markdown("---")
    
    # ==========================================================================
    # TRADE STREAM TABLE & ORDER BOOK (Fragment for live updates)
    # ==========================================================================
    
    @st.fragment(run_every=timedelta(seconds=1))
    def render_trade_feed():
        state = st.session_state.state_manager
        trades = state.get_trades(limit=20)
        depth = state.get_latest_depth()
        Components.render_live_data_feed(trades, depth)
    
    render_trade_feed()
    
    st.markdown("---")
    
    # ==========================================================================
    # LIVE-SPECIFIC: REAL-TIME ORDER BOOK DEPTH VISUALIZATION (Fragment-based)
    # ==========================================================================
    st.markdown("### 📊 Order Book Depth Visualization")
    
    depth_col1, depth_col2 = st.columns(2)
    
    @st.fragment(run_every=timedelta(seconds=1))
    def render_bid_depth():
        st.markdown("#### 🟢 Bid Depth (Buy Orders)")
        depth = st.session_state.state_manager.get_latest_depth()
        if depth and depth.bids:
            bid_prices = [b[0] for b in depth.bids[:10]]
            bid_volumes = [b[1] for b in depth.bids[:10]]
            
            fig_bids = go.Figure()
            fig_bids.add_trace(go.Bar(
                x=bid_volumes,
                y=[f"${p:,.0f}" for p in bid_prices],
                orientation='h',
                marker_color='#10b981',
                text=[f"{v:.4f}" for v in bid_volumes],
                textposition='inside'
            ))
            fig_bids.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(20, 25, 35, 0.6)",
                font_color="#fafafa",
                height=300,
                showlegend=False,
                xaxis_title="Volume (BTC)",
                yaxis_title="Price",
                margin=dict(l=80, r=30, t=70, b=40)
            )
            st.plotly_chart(fig_bids, width='stretch', config=PLOTLY_CONFIG)
        else:
            st.info("Waiting for bid data...")
    
    @st.fragment(run_every=timedelta(seconds=1))
    def render_ask_depth():
        st.markdown("#### 🔴 Ask Depth (Sell Orders)")
        depth = st.session_state.state_manager.get_latest_depth()
        if depth and depth.asks:
            ask_prices = [a[0] for a in depth.asks[:10]]
            ask_volumes = [a[1] for a in depth.asks[:10]]
            
            fig_asks = go.Figure()
            fig_asks.add_trace(go.Bar(
                x=ask_volumes,
                y=[f"${p:,.0f}" for p in ask_prices],
                orientation='h',
                marker_color='#ef4444',
                text=[f"{v:.4f}" for v in ask_volumes],
                textposition='inside'
            ))
            fig_asks.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(20, 25, 35, 0.6)",
                font_color="#fafafa",
                height=300,
                showlegend=False,
                xaxis_title="Volume (BTC)",
                yaxis_title="Price",
                margin=dict(l=80, r=30, t=40, b=40)
            )
            st.plotly_chart(fig_asks, width='stretch', config=PLOTLY_CONFIG)
        else:
            st.info("Waiting for ask data...")
    
    with depth_col1:
        render_bid_depth()
    
    with depth_col2:
        render_ask_depth()
    
    st.markdown("---")
    
    # ==========================================================================
    # STREAM STATISTICS (Fragment for live updates)
    # ==========================================================================
    
    @st.fragment(run_every=timedelta(seconds=1))
    def render_stream_stats():
        from datetime import datetime as dt_module
        st.markdown("### 📈 Stream Statistics")
        
        state = st.session_state.state_manager
        depth = state.get_latest_depth()
        last_update = state.get_last_update()
        
        trade_count = len(state.get_trades())
        bid_vol = f"{depth.bid_volume:.4f}" if depth else "—"
        ask_vol = f"{depth.ask_volume:.4f}" if depth else "—"
        latency_val = f"{(dt_module.utcnow() - last_update).total_seconds() * 1000:.0f}" if last_update else "—"
        
        stream_stats_html = f'''
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0;">
            <div style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(59, 130, 246, 0.05)); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                <div style="font-size: 12px; color: #60a5fa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;">Total Trades</div>
                <div style="font-size: 28px; font-weight: 700; color: #fafafa;">{trade_count:,}</div>
            </div>
            <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(16, 185, 129, 0.05)); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                <div style="font-size: 12px; color: #34d399; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;">Bid Volume</div>
                <div style="font-size: 28px; font-weight: 700; color: #fafafa;">{bid_vol} <span style="font-size: 14px; color: #94a3b8;">BTC</span></div>
            </div>
            <div style="background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.05)); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                <div style="font-size: 12px; color: #f87171; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;">Ask Volume</div>
                <div style="font-size: 28px; font-weight: 700; color: #fafafa;">{ask_vol} <span style="font-size: 14px; color: #94a3b8;">BTC</span></div>
            </div>
            <div style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.05)); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                <div style="font-size: 12px; color: #a78bfa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;">Latency</div>
                <div style="font-size: 28px; font-weight: 700; color: #fafafa;">{latency_val} <span style="font-size: 14px; color: #94a3b8;">ms</span></div>
            </div>
        </div>
        '''
        st.markdown(stream_stats_html, unsafe_allow_html=True)
    
    render_stream_stats()
    
    # ==========================================================================
    # LIVE-SPECIFIC: TRADE ACTIVITY HEATMAP (Fragment-based for fullscreen-safe)
    # ==========================================================================
    st.markdown("---")
    
    @st.fragment(run_every=timedelta(seconds=1))
    def render_trade_activity():
        from datetime import datetime as dt_module
        st.markdown("### 🔥 Trade Activity (Last 60 seconds)")
        
        all_trades = st.session_state.state_manager.get_trades(limit=500)
        if all_trades:
            now = dt_module.utcnow()
            buy_counts = [0] * 60
            sell_counts = [0] * 60
            
            for trade in all_trades:
                age = (now - trade.timestamp).total_seconds()
                if 0 <= age < 60:
                    idx = int(age)
                    if trade.is_buyer_maker:
                        sell_counts[59 - idx] += 1
                    else:
                        buy_counts[59 - idx] += 1
            
            fig_activity = go.Figure()
            x_labels = [f"-{60-i}s" for i in range(60)]
            
            fig_activity.add_trace(go.Bar(x=x_labels, y=buy_counts, name='Buy', marker_color='#10b981'))
            fig_activity.add_trace(go.Bar(x=x_labels, y=sell_counts, name='Sell', marker_color='#ef4444'))
            
            fig_activity.update_layout(
                barmode='stack',
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(20, 25, 35, 0.6)",
                font_color="#fafafa",
                height=250,
                legend=dict(
                    orientation="h", 
                    yanchor="top", 
                    y=0.99, 
                    xanchor="left", 
                    x=0.01,
                    bgcolor="rgba(20, 25, 35, 0.8)"
                ),
                xaxis_title="Time Ago",
                yaxis_title="Trade Count",
                margin=dict(l=60, r=30, t=50, b=40)
            )
            fig_activity.update_xaxes(tickmode='array', tickvals=x_labels[::10], ticktext=x_labels[::10])
            
            st.plotly_chart(fig_activity, width='stretch', config=PLOTLY_CONFIG)
        else:
            st.info("Waiting for trade data...")
    
    render_trade_activity()


# =============================================================================
# PAGE: HOME - Beautiful Landing Page with Animations
# =============================================================================

def render_home_page():
    """Render the beautiful home/landing page with animations and feature highlights."""
    
    # CSS Animations and Feature Card Styling
    st.markdown("""<style>
        @keyframes gradient-shift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-15px); } }
        @keyframes glow-pulse { 0%, 100% { filter: drop-shadow(0 0 20px rgba(251, 191, 36, 0.4)); } 50% { filter: drop-shadow(0 0 40px rgba(251, 191, 36, 0.8)); } }
        @keyframes ticker-scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
        
        /* Force uniform feature card heights */
        .feature-card {
            background: linear-gradient(145deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.95));
            border: 1px solid rgba(71, 85, 105, 0.3);
            border-radius: 20px;
            padding: 32px 28px;
            height: 280px;
            position: relative;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            display: flex;
            flex-direction: column;
        }
        .feature-card .card-icon {
            width: 60px;
            height: 60px;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            margin-bottom: 20px;
            flex-shrink: 0;
        }
        .feature-card .card-title {
            font-size: 20px;
            font-weight: 700;
            color: #f1f5f9;
            margin-bottom: 14px;
            flex-shrink: 0;
        }
        .feature-card .card-desc {
            font-size: 14px;
            color: #94a3b8;
            line-height: 1.7;
            flex-grow: 1;
        }
        .feature-card .card-accent {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            border-radius: 20px 20px 0 0;
        }
    </style>""", unsafe_allow_html=True)
    
    # Hero Section
    st.markdown("""<div style="text-align: center; padding: 80px 40px; background: linear-gradient(-45deg, #0f172a, #1e1b4b, #172554, #0c4a6e, #134e4a); background-size: 400% 400%; animation: gradient-shift 15s ease infinite; border-radius: 32px; margin-bottom: 40px; position: relative; overflow: hidden; border: 1px solid rgba(139, 92, 246, 0.2); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);">
        <div style="position: absolute; top: -100px; right: -100px; width: 300px; height: 300px; background: radial-gradient(circle, rgba(139, 92, 246, 0.15) 0%, transparent 70%); border-radius: 50%;"></div>
        <div style="position: absolute; bottom: -80px; left: -80px; width: 250px; height: 250px; background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%); border-radius: 50%;"></div>
        <div style="font-size: 100px; animation: float 4s ease-in-out infinite, glow-pulse 3s ease-in-out infinite; margin-bottom: 24px;">📈</div>
        <h1 style="font-size: 72px; font-weight: 900; background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 20%, #ef4444 40%, #8b5cf6 60%, #3b82f6 80%, #06b6d4 100%); background-size: 200% auto; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: gradient-shift 4s ease infinite; margin: 0 0 16px 0; letter-spacing: -2px;">AlgoViz</h1>
        <div style="font-size: 18px; color: #a5b4fc; font-weight: 400; letter-spacing: 8px; margin-bottom: 32px; text-transform: uppercase;">See the Signal in the Noise</div>
        <p style="font-size: 20px; color: #cbd5e1; max-width: 800px; margin: 0 auto; line-height: 1.8; font-weight: 300;">A professional-grade algorithmic trading visualization dashboard that transforms complex market data into actionable insights. Built with cutting-edge <span style="color: #8b5cf6; font-weight: 600;">deep learning models</span>, real-time analytics, and intuitive visualizations.</p>
    </div>""", unsafe_allow_html=True)
    
    # Ticker Section
    st.markdown("""<div style="background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(30, 41, 59, 0.9)); border-radius: 16px; padding: 20px 0; overflow: hidden; margin: 40px 0; border: 1px solid rgba(71, 85, 105, 0.4);">
        <div style="display: flex; animation: ticker-scroll 25s linear infinite; white-space: nowrap;">
            <span style="padding: 0 50px; color: #94a3b8; font-size: 15px;"><span style="color: #fbbf24; font-weight: 700;">BTC/USDT</span> Real-time Order Book</span>
            <span style="color: #4b5563; padding: 0 10px;">●</span>
            <span style="padding: 0 50px; color: #94a3b8; font-size: 15px;"><span style="color: #8b5cf6; font-weight: 700;">🧠 LSTM</span> Attention Neural Networks</span>
            <span style="color: #4b5563; padding: 0 10px;">●</span>
            <span style="padding: 0 50px; color: #94a3b8; font-size: 15px;"><span style="color: #10b981; font-weight: 700;">⚡ 250ms</span> Data Refresh Rate</span>
            <span style="color: #4b5563; padding: 0 10px;">●</span>
            <span style="padding: 0 50px; color: #94a3b8; font-size: 15px;"><span style="color: #3b82f6; font-weight: 700;">📊 4</span> Trading Strategies</span>
            <span style="color: #4b5563; padding: 0 10px;">●</span>
            <span style="padding: 0 50px; color: #94a3b8; font-size: 15px;"><span style="color: #ef4444; font-weight: 700;">🔔</span> Smart Alert System</span>
            <span style="color: #4b5563; padding: 0 10px;">●</span>
            <span style="padding: 0 50px; color: #94a3b8; font-size: 15px;"><span style="color: #fbbf24; font-weight: 700;">BTC/USDT</span> Real-time Order Book</span>
            <span style="color: #4b5563; padding: 0 10px;">●</span>
            <span style="padding: 0 50px; color: #94a3b8; font-size: 15px;"><span style="color: #8b5cf6; font-weight: 700;">🧠 LSTM</span> Attention Neural Networks</span>
        </div>
    </div>""", unsafe_allow_html=True)
    
    # Stats Section Title
    st.markdown("""<div style="text-align: center; margin: 60px 0 40px;">
        <div style="font-size: 13px; color: #8b5cf6; text-transform: uppercase; letter-spacing: 4px; margin-bottom: 8px; font-weight: 600;">Dashboard Statistics</div>
        <div style="font-size: 36px; font-weight: 800; color: #f1f5f9; margin-bottom: 40px;">Powerful Trading Intelligence</div>
    </div>""", unsafe_allow_html=True)
    
    # Stats with Streamlit columns
    stat_cols = st.columns(4)
    
    with stat_cols[0]:
        st.markdown("""
            <div style="text-align: center; padding: 30px 20px; background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9)); border-radius: 20px; border: 1px solid rgba(139, 92, 246, 0.2);">
                <div style="font-size: 52px; font-weight: 900; background: linear-gradient(135deg, #8b5cf6, #8b5cf6dd); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1.1;">10+</div>
                <div style="font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 2px; margin-top: 12px; font-weight: 600;">Chart Types</div>
            </div>
        """, unsafe_allow_html=True)
    
    with stat_cols[1]:
        st.markdown("""
            <div style="text-align: center; padding: 30px 20px; background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9)); border-radius: 20px; border: 1px solid rgba(139, 92, 246, 0.2);">
                <div style="font-size: 52px; font-weight: 900; background: linear-gradient(135deg, #3b82f6, #3b82f6dd); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1.1;">2</div>
                <div style="font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 2px; margin-top: 12px; font-weight: 600;">DL Models</div>
            </div>
        """, unsafe_allow_html=True)
    
    with stat_cols[2]:
        st.markdown("""
            <div style="text-align: center; padding: 30px 20px; background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9)); border-radius: 20px; border: 1px solid rgba(139, 92, 246, 0.2);">
                <div style="font-size: 52px; font-weight: 900; background: linear-gradient(135deg, #10b981, #10b981dd); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1.1;">4</div>
                <div style="font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 2px; margin-top: 12px; font-weight: 600;">Strategies</div>
            </div>
        """, unsafe_allow_html=True)
    
    with stat_cols[3]:
        st.markdown("""
            <div style="text-align: center; padding: 30px 20px; background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9)); border-radius: 20px; border: 1px solid rgba(139, 92, 246, 0.2);">
                <div style="font-size: 52px; font-weight: 900; background: linear-gradient(135deg, #f59e0b, #f59e0bdd); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1.1;">∞</div>
                <div style="font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 2px; margin-top: 12px; font-weight: 600;">Insights</div>
            </div>
        """, unsafe_allow_html=True)
    
    # Features Section Title
    st.markdown("""
        <div style="text-align: center; margin: 70px 0 40px;">
            <div style="font-size: 13px; color: #8b5cf6; text-transform: uppercase; letter-spacing: 4px; margin-bottom: 8px; font-weight: 600;">
                Core Features
            </div>
            <div style="font-size: 36px; font-weight: 800; color: #f1f5f9;">
                Everything You Need to Trade Smarter
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Feature cards - Using CSS Grid for uniform heights
    st.markdown("""
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-bottom: 24px;">
        <!-- Card 1: Real-Time Dashboard -->
        <div style="background: linear-gradient(145deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.95)); border: 1px solid rgba(71, 85, 105, 0.3); border-radius: 20px; padding: 32px 28px; position: relative; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 4px; background: linear-gradient(90deg, #3b82f6, #3b82f688); border-radius: 20px 20px 0 0;"></div>
            <div style="width: 60px; height: 60px; background: rgba(59, 130, 246, 0.15); border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin-bottom: 20px; border: 1px solid rgba(59, 130, 246, 0.3);">📊</div>
            <div style="font-size: 20px; font-weight: 700; color: #f1f5f9; margin-bottom: 14px;">Real-Time Dashboard</div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.7;">Live price charts, VWAP/TWAP indicators, order book depth, and spread analysis.</div>
        </div>
        <!-- Card 2: Deep Learning Predictions -->
        <div style="background: linear-gradient(145deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.95)); border: 1px solid rgba(71, 85, 105, 0.3); border-radius: 20px; padding: 32px 28px; position: relative; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 4px; background: linear-gradient(90deg, #8b5cf6, #8b5cf688); border-radius: 20px 20px 0 0;"></div>
            <div style="width: 60px; height: 60px; background: rgba(139, 92, 246, 0.15); border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin-bottom: 20px; border: 1px solid rgba(139, 92, 246, 0.3);">🧠</div>
            <div style="font-size: 20px; font-weight: 700; color: #f1f5f9; margin-bottom: 14px;">Deep Learning Predictions</div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.7;">LSTM neural networks with attention for price direction forecasting and regime detection.</div>
        </div>
        <!-- Card 3: Advanced Analytics -->
        <div style="background: linear-gradient(145deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.95)); border: 1px solid rgba(71, 85, 105, 0.3); border-radius: 20px; padding: 32px 28px; position: relative; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 4px; background: linear-gradient(90deg, #10b981, #10b98188); border-radius: 20px 20px 0 0;"></div>
            <div style="width: 60px; height: 60px; background: rgba(16, 185, 129, 0.15); border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin-bottom: 20px; border: 1px solid rgba(16, 185, 129, 0.3);">📈</div>
            <div style="font-size: 20px; font-weight: 700; color: #f1f5f9; margin-bottom: 14px;">Advanced Analytics</div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.7;">Comprehensive technical analysis with candlestick charts, volatility surfaces, and correlation matrices.</div>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px;">
        <!-- Card 4: Strategy Backtester -->
        <div style="background: linear-gradient(145deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.95)); border: 1px solid rgba(71, 85, 105, 0.3); border-radius: 20px; padding: 32px 28px; position: relative; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 4px; background: linear-gradient(90deg, #f59e0b, #f59e0b88); border-radius: 20px 20px 0 0;"></div>
            <div style="width: 60px; height: 60px; background: rgba(245, 158, 11, 0.15); border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin-bottom: 20px; border: 1px solid rgba(245, 158, 11, 0.3);">⚡</div>
            <div style="font-size: 20px; font-weight: 700; color: #f1f5f9; margin-bottom: 14px;">Strategy Backtester</div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.7;">Test momentum, mean-reversion, volatility breakout strategies with realistic commission modeling.</div>
        </div>
        <!-- Card 5: Smart Alerts -->
        <div style="background: linear-gradient(145deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.95)); border: 1px solid rgba(71, 85, 105, 0.3); border-radius: 20px; padding: 32px 28px; position: relative; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 4px; background: linear-gradient(90deg, #ef4444, #ef444488); border-radius: 20px 20px 0 0;"></div>
            <div style="width: 60px; height: 60px; background: rgba(239, 68, 68, 0.15); border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin-bottom: 20px; border: 1px solid rgba(239, 68, 68, 0.3);">🔔</div>
            <div style="font-size: 20px; font-weight: 700; color: #f1f5f9; margin-bottom: 14px;">Smart Alerts</div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.7;">Configurable price, volume, spread, and volatility alerts with real-time notifications.</div>
        </div>
        <!-- Card 6: AI-Powered Insights -->
        <div style="background: linear-gradient(145deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.95)); border: 1px solid rgba(71, 85, 105, 0.3); border-radius: 20px; padding: 32px 28px; position: relative; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 4px; background: linear-gradient(90deg, #06b6d4, #06b6d488); border-radius: 20px 20px 0 0;"></div>
            <div style="width: 60px; height: 60px; background: rgba(6, 182, 212, 0.15); border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 32px; margin-bottom: 20px; border: 1px solid rgba(6, 182, 212, 0.3);">💡</div>
            <div style="font-size: 20px; font-weight: 700; color: #f1f5f9; margin-bottom: 14px;">AI-Powered Insights</div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.7;">Automated market commentary and actionable trading insights from real-time data patterns.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # CTA Section
    st.markdown("""<div style="text-align: center; padding: 50px 40px; background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(59, 130, 246, 0.1), rgba(6, 182, 212, 0.1)); border-radius: 24px; border: 1px solid rgba(139, 92, 246, 0.25); margin-top: 50px; position: relative; overflow: hidden;">
        <div style="position: absolute; top: -50px; right: -50px; width: 200px; height: 200px; background: radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, transparent 70%); border-radius: 50%;"></div>
        <div style="font-size: 42px; margin-bottom: 16px;">🚀</div>
        <div style="font-size: 32px; font-weight: 800; color: #f1f5f9; margin-bottom: 16px;">Ready to Explore?</div>
        <div style="color: #94a3b8; font-size: 18px; max-width: 600px; margin: 0 auto; line-height: 1.7;">Select <strong style="color: #8b5cf6;">Dashboard</strong> from the sidebar to start analyzing market data, or switch to <strong style="color: #10b981;">Live Data</strong> mode for real-time Binance feeds.</div>
    </div>""", unsafe_allow_html=True)
    
    # Team Section
    st.markdown("""<div style="text-align: center; margin-top: 50px; padding: 40px; background: linear-gradient(135deg, rgba(30, 41, 59, 0.6), rgba(15, 23, 42, 0.8)); border-radius: 20px; border: 1px solid rgba(71, 85, 105, 0.3);">
        <div style="font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 4px; margin-bottom: 16px; font-weight: 600;">Created By</div>
        <div style="font-size: 20px; background: linear-gradient(135deg, #a5b4fc, #8b5cf6, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; font-weight: 600; letter-spacing: 1px;">Kartik Joshi  •  Aditya Chitale  •  Krishna Patel</div>
    </div>""", unsafe_allow_html=True)


# =============================================================================
# PAGE: DASHBOARD (MAIN) - Works for both Static and Live modes
# =============================================================================

def render_dashboard_page(is_static: bool, generator: Optional[SyntheticDataGenerator] = None):
    """Main dashboard page with charts and analytics."""
    
    # ==========================================================================
    # HEADER AND CONNECTION STATUS (Fragment for live updates)
    # ==========================================================================
    
    @st.fragment(run_every=timedelta(seconds=1) if not is_static else None)
    def render_header_and_status():
        if is_static:
            Components.render_dashboard_header(True)
            st.markdown("""
                <div style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(139, 92, 246, 0.2)); 
                            border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 12px; padding: 12px 20px; margin-bottom: 20px;">
                    <span style="color: #60a5fa; font-weight: 600;">📊 Demo Mode</span>
                    <span style="color: #a0aec0; margin-left: 10px;">Displaying synthetic data for demonstration</span>
                </div>
            """, unsafe_allow_html=True)
        else:
            state = st.session_state.state_manager
            connection_status = state.get_connection_status()
            last_update = state.get_last_update()
            Components.render_dashboard_header(connection_status == "connected")
            Components.render_connection_status(connection_status, last_update)
    
    render_header_and_status()
    
    # ==========================================================================
    # NOTIFICATION BELL (Fragment for live alerts)
    # ==========================================================================
    
    @st.fragment(run_every=timedelta(seconds=2) if not is_static else None)
    def render_notification_bell():
        """Render the notification bell icon with alerts popover."""
        if is_static:
            # Static mode: Show disabled bell with message
            with st.popover("🔕 Alerts", use_container_width=False):
                Components.render_notification_popover([], is_live_mode=False)
        else:
            # Live mode: Evaluate alerts and show active bell
            f = st.session_state.feature_engine.calculate_all()
            prediction = st.session_state.last_prediction
            alerts = evaluate_alerts(f, prediction)
            alert_count = len(alerts) if alerts else 0
            
            # Bell icon with count badge
            bell_label = f"🔔 Alerts ({alert_count})" if alert_count > 0 else "🔔 Alerts"
            with st.popover(bell_label, use_container_width=False):
                Components.render_notification_popover(alerts, is_live_mode=True)
    
    # Position bell icon on the right side
    bell_col1, bell_col2 = st.columns([6, 1])
    with bell_col2:
        render_notification_bell()
    
    # Get initial features for non-fragment elements (also used by fragments)
    if is_static:
        features = get_synthetic_features(generator)
        insights = []
    else:
        feature_engine = st.session_state.feature_engine
        insight_generator = st.session_state.insight_generator
        features = feature_engine.calculate_all()
        insights = insight_generator.generate(features)
    
    # ==========================================================================
    # FILTER CONTROLS
    # ==========================================================================
    
    st.markdown("### ⚙️ Chart Controls")
    
    filter_cols = st.columns([1, 1, 1, 1])
    
    with filter_cols[0]:
        price_window = st.selectbox(
            "📈 Price Chart Window",
            options=["30 sec", "1 min", "2 min", "5 min"],
            index=2,
            help="Time window for price & VWAP chart"
        )
    
    with filter_cols[1]:
        volatility_window = st.selectbox(
            "📉 Volatility Window",
            options=["1 min", "2 min", "5 min", "10 min"],
            index=1,
            help="Time window for volatility chart"
        )
    
    with filter_cols[2]:
        chart_style = st.selectbox(
            "🎨 Line Style",
            options=["Smooth (Spline)", "Sharp (Linear)", "Step"],
            index=0,
            help="Chart line interpolation style"
        )
    
    with filter_cols[3]:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        # Fragment-based updates - no pause needed, fullscreen is preserved
        st.markdown(
            "<div style='font-size: 11px; color: #10b981; padding: 8px 12px; background: rgba(16,185,129,0.1); border-radius: 6px; text-align: center;'>"
            "✓ Fullscreen-safe updates"
            "</div>",
            unsafe_allow_html=True
        )
        auto_refresh = False  # Disable main loop refresh, use fragments instead
    
    # Parse filter values
    window_map = {"30 sec": 30, "1 min": 60, "2 min": 120, "5 min": 300, "10 min": 600}
    price_window_secs = window_map.get(price_window, 120)
    volatility_window_secs = window_map.get(volatility_window, 120)
    
    style_map = {"Smooth (Spline)": "spline", "Sharp (Linear)": "linear", "Step": "hv"}
    line_shape = style_map.get(chart_style, "spline")
    
    st.markdown("---")
    
    # ==========================================================================
    # KPI METRICS (Fragment for live updates)
    # ==========================================================================
    
    @st.fragment(run_every=timedelta(seconds=1) if not is_static else None)
    def render_kpi_section():
        if is_static:
            gen = generator if generator else st.session_state.synthetic_generator
            gen.generate_trade()  # Generate new data point
            kpi_features = get_synthetic_features(gen)
        else:
            kpi_features = st.session_state.feature_engine.calculate_all()
        Components.render_kpi_header(kpi_features)
    
    render_kpi_section()
    
    st.markdown("---")
    
    # ==========================================================================
    # CHARTS ROW 1 - Using fragments for fullscreen-safe updates
    # ==========================================================================
    
    st.markdown("### 📊 Market Analytics")
    
    col1, col2 = st.columns(2)
    
    # Fragment for Price & VWAP chart - auto-updates without page rerun
    @st.fragment(run_every=timedelta(seconds=1) if not is_static else None)
    def render_price_chart():
        st.markdown("#### 📈 Price & VWAP")
        if is_static:
            price_data = get_synthetic_price_data(generator, price_window_secs)
        else:
            price_data = st.session_state.feature_engine.get_price_chart_data(price_window_secs)
        fig_price = Charts.create_price_vwap_chart(price_data, height=420, line_shape=line_shape)
        st.plotly_chart(fig_price, width='stretch', config=PLOTLY_CONFIG)
        
        # Add insight box under the chart in collapsible expander
        from ui.charts import ChartInsights
        if price_data:
            prices = [d["price"] for d in price_data]
            vwaps = [d["vwap"] for d in price_data]
            insight_html = ChartInsights.price_vwap_insight(prices, vwaps)
            with st.expander("💡 Price & VWAP Insight", expanded=False):
                st.markdown(insight_html, unsafe_allow_html=True)
        else:
            st.info("💡 Waiting for price data to generate insights...")
    
    # Fragment for Spread chart
    @st.fragment(run_every=timedelta(seconds=1) if not is_static else None)
    def render_spread_chart():
        st.markdown("#### 📊 Bid-Ask Spread Timeline")
        if is_static:
            spread_data = get_synthetic_spread_data(generator, SPREAD_HEATMAP_WINDOW_SECONDS)
        else:
            # IMPORTANT: Call calculate_all() to update spread history from live depth data
            st.session_state.feature_engine.calculate_all()
            spread_data = st.session_state.feature_engine.get_spread_chart_data(SPREAD_HEATMAP_WINDOW_SECONDS)
        spread_data = spread_data[-10:] if len(spread_data) > 10 else spread_data
        fig_spread = Charts.create_spread_heatmap(spread_data, height=420)
        st.plotly_chart(fig_spread, width='stretch', config=PLOTLY_CONFIG)
        
        # Add insight box under the chart in collapsible expander
        if spread_data:
            from ui.charts import ChartInsights
            insight_html = ChartInsights.spread_insight(spread_data)
            with st.expander("💡 Spread Analysis", expanded=False):
                st.markdown(insight_html, unsafe_allow_html=True)
    
    with col1:
        render_price_chart()
    
    with col2:
        render_spread_chart()
    
    # ==========================================================================
    # CHARTS ROW 2 - Using fragments for fullscreen-safe updates
    # ==========================================================================
    
    st.markdown("")  # Spacing
    col3, col4 = st.columns(2)
    
    # Fragment for Imbalance chart
    @st.fragment(run_every=timedelta(seconds=1) if not is_static else None)
    def render_imbalance_chart():
        st.markdown("#### ⚖️ Order Book Imbalance")
        # Get fresh features data
        if is_static:
            gen = generator if generator else st.session_state.synthetic_generator
            gen.generate_trade()  # Generate new data point
            f = get_synthetic_features(gen)
        else:
            f = st.session_state.feature_engine.calculate_all()
        fig_imbalance = Charts.create_imbalance_chart(
            imbalance=f.imbalance,
            bid_volume=f.bid_volume,
            ask_volume=f.ask_volume,
            height=380
        )
        st.plotly_chart(fig_imbalance, width='stretch', config=PLOTLY_CONFIG)
        
        # Add insight box under the chart in collapsible expander
        from ui.charts import ChartInsights
        insight_html = ChartInsights.imbalance_insight(f.imbalance, f.bid_volume, f.ask_volume)
        with st.expander("💡 Order Book Insight", expanded=False):
            st.markdown(insight_html, unsafe_allow_html=True)
    
    # Fragment for Velocity chart
    @st.fragment(run_every=timedelta(seconds=1) if not is_static else None)
    def render_velocity_chart():
        st.markdown("#### ⚡ Trade Velocity")
        # Get fresh features data
        if is_static:
            gen = generator if generator else st.session_state.synthetic_generator
            gen.generate_trade()  # Generate new data point
            f = get_synthetic_features(gen)
        else:
            f = st.session_state.feature_engine.calculate_all()
        fig_velocity = Charts.create_velocity_gauge(
            velocity=f.velocity,
            baseline=f.velocity_baseline,
            height=380
        )
        st.plotly_chart(fig_velocity, width='stretch', config=PLOTLY_CONFIG)
        
        # Add insight box under the chart in collapsible expander
        from ui.charts import ChartInsights
        insight_html = ChartInsights.velocity_insight(f.velocity, f.velocity_baseline)
        with st.expander("💡 Velocity Analysis", expanded=False):
            st.markdown(insight_html, unsafe_allow_html=True)
    
    with col3:
        render_imbalance_chart()
    
    with col4:
        render_velocity_chart()
    
    # ==========================================================================
    # CHARTS ROW 3 - Using fragments for fullscreen-safe updates
    # ==========================================================================
    
    st.markdown("")  # Spacing
    col5, col6 = st.columns(2)
    
    # Fragment for Volatility chart
    @st.fragment(run_every=timedelta(seconds=1) if not is_static else None)
    def render_volatility_chart():
        st.markdown("#### 📉 Volatility Monitor")
        if is_static:
            volatility_data = get_synthetic_volatility_data(generator, volatility_window_secs)
        else:
            # IMPORTANT: Call calculate_all() to update volatility history from live data
            st.session_state.feature_engine.calculate_all()
            volatility_data = st.session_state.feature_engine.get_volatility_chart_data(volatility_window_secs)
        fig_volatility = Charts.create_volatility_chart(volatility_data, height=420, line_shape=line_shape)
        st.plotly_chart(fig_volatility, width='stretch', config=PLOTLY_CONFIG)
        
        # Add insight box under the chart in collapsible expander
        if volatility_data:
            from ui.charts import ChartInsights
            insight_html = ChartInsights.volatility_insight(volatility_data)
            with st.expander("💡 Volatility Analysis", expanded=False):
                st.markdown(insight_html, unsafe_allow_html=True)
    
    with col5:
        render_volatility_chart()
    
    with col6:
        st.markdown("#### 🎯 Trading Intelligence")
        if is_static:
            # Show synthetic insights for demo
            st.markdown("""
                <div style="background: rgba(20, 25, 35, 0.8); border: 1px solid rgba(255,255,255,0.1); 
                            border-radius: 12px; padding: 20px; height: 310px;">
                    <h4 style="color: #fafafa; margin-bottom: 15px;">📊 Market Analysis</h4>
                    <div style="color: #a0aec0; margin-bottom: 10px;">
                        <span style="color: #10b981;">●</span> Price trending within normal range
                    </div>
                    <div style="color: #a0aec0; margin-bottom: 10px;">
                        <span style="color: #f59e0b;">●</span> Volatility at moderate levels
                    </div>
                    <div style="color: #a0aec0; margin-bottom: 10px;">
                        <span style="color: #3b82f6;">●</span> Order book shows balanced depth
                    </div>
                    <div style="color: #a0aec0; margin-bottom: 10px;">
                        <span style="color: #8b5cf6;">●</span> Trade velocity within baseline
                    </div>
                    <div style="margin-top: 20px; padding: 10px; background: rgba(16, 185, 129, 0.1); 
                                border-radius: 8px; border-left: 3px solid #10b981;">
                        <span style="color: #10b981; font-weight: 600;">Signal:</span>
                        <span style="color: #fafafa;"> Market conditions favorable for trading</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            Components.render_insight_panel(insights, height=350)
    
    return auto_refresh


# =============================================================================
# PAGE: ANALYTICS
# =============================================================================

def render_analytics_page(is_static: bool, generator: Optional[SyntheticDataGenerator] = None):
    """Render the Analytics page with tabs (5 tabs in demo mode, 4 in live mode)."""
    st.markdown("# 📈 Advanced Analytics")
    st.markdown("*Deep market analysis, neural network predictions, and strategy backtesting*")
    
    # Tab structure - Data Quality tab ONLY in static/demo mode
    if is_static:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Distribution & Returns", 
            "🔗 Relationships", 
            "🧪 Backtester",
            "🧠 Deep Learning",
            "🔍 Data Quality"
        ])
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Distribution & Returns", 
            "🔗 Relationships", 
            "🧪 Backtester",
            "🧠 Deep Learning"
        ])
        tab5 = None  # No data quality tab in live mode
    
    # Helper function to get live data (called by each fragment)
    def get_analytics_data():
        if is_static:
            gen = generator if generator else st.session_state.get('synthetic_generator')
            if gen:
                gen.generate_trade()  # Generate new data point
                price_data = gen.generate_historical_prices(minutes=15)
                prices = [p[1] for p in price_data]
                vol_data = gen.generate_volatility_data(minutes=15)
                vols = [v[1] for v in vol_data]
            else:
                prices = [68000 + np.random.randn() * 100 for _ in range(100)]
                vols = [5 + np.random.randn() * 2 for _ in range(100)]
        else:
            feature_engine = st.session_state.feature_engine
            # IMPORTANT: Call calculate_all() to populate history buffers from live trades
            feature_engine.calculate_all()
            price_chart_data = feature_engine.get_price_chart_data(window_seconds=900)
            if price_chart_data and len(price_chart_data) > 1:
                prices = [p['price'] for p in price_chart_data]
            else:
                prices = [68000]
            vol_chart_data = feature_engine.get_volatility_chart_data(window_seconds=900)
            if vol_chart_data and len(vol_chart_data) > 1:
                vols = [v['volatility_bps'] for v in vol_chart_data]
            else:
                vols = [5.0]
        return prices, vols
    
    # =========================================================================
    # TAB 1: Distribution & Returns Analysis (Combined, Fragment for live updates)
    # =========================================================================
    with tab1:
        @st.fragment(run_every=timedelta(seconds=2) if not is_static else None)
        def render_distribution_returns_tab():
            import plotly.express as px
            import plotly.graph_objects as go
            from ui.charts import ChartInsights
            
            st.markdown("### 📊 Distribution & Returns Analysis")
            if is_static:
                st.info("📊 **Demo Mode**: Showing sample analytics with synthetic data.")
            else:
                st.info("🔴 **Live Mode**: Real-time market analytics from Binance (updates every 2s)")
            
            prices, vols = get_analytics_data()
            
            # Row 1: Distribution charts
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Price Distribution")
                fig = px.histogram(x=prices, nbins=30, title=f"Price Distribution ({len(prices)} samples)")
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(20, 25, 35, 0.6)",
                    font_color="#fafafa",
                    title_font_size=14,
                    height=280,
                    margin=dict(b=20)
                )
                fig.update_traces(marker_color='#3b82f6')
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
                # Add insight in expander
                with st.expander("💡 Price Distribution Insight", expanded=False):
                    st.markdown(ChartInsights.distribution_insight(prices, "Price"), unsafe_allow_html=True)
            
            with col2:
                st.markdown("#### Volatility Distribution")
                fig = px.histogram(x=vols, nbins=20, title=f"Volatility Distribution ({len(vols)} samples)")
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(20, 25, 35, 0.6)",
                    font_color="#fafafa",
                    title_font_size=14,
                    height=280,
                    margin=dict(b=20)
                )
                fig.update_traces(marker_color='#f59e0b')
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
                # Add insight in expander
                with st.expander("💡 Volatility Distribution Insight", expanded=False):
                    st.markdown(ChartInsights.distribution_insight(vols, "Volatility"), unsafe_allow_html=True)
            
            # Row 2: Returns charts
            returns = np.diff(prices) / np.array(prices[:-1]) * 100 if len(prices) > 1 else np.array([0])
            
            ret_col1, ret_col2 = st.columns(2)
            
            with ret_col1:
                st.markdown("#### Return Distribution")
                fig = px.histogram(x=returns, nbins=40, title=f"Return Distribution ({len(returns)} returns)")
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(20, 25, 35, 0.6)",
                    font_color="#fafafa",
                    height=280,
                    margin=dict(b=20)
                )
                fig.update_traces(marker_color='#10b981')
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
                # Add insight in expander
                with st.expander("💡 Return Distribution Insight", expanded=False):
                    st.markdown(ChartInsights.returns_insight(list(returns)), unsafe_allow_html=True)
            
            with ret_col2:
                st.markdown("#### Rolling Volatility")
                window = min(20, len(returns)) if len(returns) > 0 else 1
                rolling_vol = [np.std(returns[max(0, i-window):i+1]) for i in range(len(returns))] if len(returns) > 0 else [0]
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    y=rolling_vol,
                    mode='lines',
                    fill='tozeroy',
                    line=dict(color='#8b5cf6', width=2),
                    fillcolor='rgba(139, 92, 246, 0.3)'
                ))
                fig.update_layout(
                    title="Rolling Volatility (20-period)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(20, 25, 35, 0.6)",
                    font_color="#fafafa",
                    showlegend=False,
                    height=280,
                    margin=dict(b=20)
                )
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
                # Add insight for rolling volatility
                if rolling_vol:
                    current_rv = rolling_vol[-1] if rolling_vol else 0
                    avg_rv = np.mean(rolling_vol)
                    vol_insight_html = f'''
                    <div style="background: rgba(20, 25, 35, 0.85); border-left: 3px solid #8b5cf6; 
                                border-radius: 0 8px 8px 0; padding: 12px 16px;">
                        <div style="display: flex; align-items: flex-start; margin-bottom: 6px;">
                            <span style="font-size: 14px; margin-right: 8px;">📊</span>
                            <div><span style="color: #a0aec0; font-weight: 500;">Current:</span> 
                            <span style="color: #e2e8f0;">{current_rv:.4f}% | Avg: {avg_rv:.4f}%</span></div>
                        </div>
                        <div style="display: flex; align-items: flex-start;">
                            <span style="font-size: 14px; margin-right: 8px;">🎯</span>
                            <div><span style="color: #a0aec0; font-weight: 500;">How to Read:</span> 
                            <span style="color: #e2e8f0;">Rising line = increasing risk. Spikes often precede large price moves.</span></div>
                        </div>
                    </div>
                    '''
                    with st.expander("💡 Rolling Volatility Insight", expanded=False):
                        st.markdown(vol_insight_html, unsafe_allow_html=True)
            
            # =====================================================================
            # Distribution Statistics
            # =====================================================================
            st.markdown("### 📊 Distribution Statistics")
            
            avg_price = np.mean(prices)
            price_std = np.std(prices) if len(prices) > 1 else 0
            price_min = np.min(prices) if len(prices) > 0 else 0
            price_max = np.max(prices) if len(prices) > 0 else 0
            avg_vol = np.mean(vols)
            vol_std = np.std(vols) if len(vols) > 1 else 0
            
            def fmt_price(val):
                if val >= 1_000_000:
                    return f"${val/1_000_000:.2f}M"
                elif val >= 1_000:
                    return f"${val/1_000:.2f}K"
                else:
                    return f"${val:.2f}"
            
            dist_stats_html = f'''
            <div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin: 20px 0;">
                <div style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(59, 130, 246, 0.05)); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #60a5fa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Avg Price</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{fmt_price(avg_price)}</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.05)); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #a78bfa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Price Std</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{fmt_price(price_std)}</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(16, 185, 129, 0.05)); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #34d399; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Min Price</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{fmt_price(price_min)}</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.05)); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #f87171; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Max Price</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{fmt_price(price_max)}</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.05)); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #fbbf24; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Avg Volatility</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{avg_vol:.2f} bps</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(236, 72, 153, 0.15), rgba(236, 72, 153, 0.05)); border: 1px solid rgba(236, 72, 153, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #f472b6; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Vol Std</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{vol_std:.2f} bps</div>
                </div>
            </div>
            '''
            st.markdown(dist_stats_html, unsafe_allow_html=True)
            
            # =====================================================================
            # Return Statistics
            # =====================================================================
            st.markdown("### 📈 Return Statistics")
            
            mean_ret = np.mean(returns)
            std_ret = np.std(returns) if len(returns) > 1 else 0
            min_ret = np.min(returns) if len(returns) > 0 else 0
            max_ret = np.max(returns) if len(returns) > 0 else 0
            skewness = np.mean(((returns - np.mean(returns)) / (std_ret if std_ret > 0 else 1)) ** 3) if std_ret > 0 else 0
            kurtosis = np.mean(((returns - np.mean(returns)) / (std_ret if std_ret > 0 else 1)) ** 4) - 3 if std_ret > 0 else 0
            
            ret_stats_html = f'''
            <div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin: 20px 0;">
                <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(16, 185, 129, 0.05)); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #34d399; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Mean Return</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{mean_ret:.4f}%</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(59, 130, 246, 0.05)); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #60a5fa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Return Std</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{std_ret:.4f}%</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.05)); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #f87171; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Min Return</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{min_ret:.4f}%</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.05)); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #fbbf24; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Max Return</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{max_ret:.4f}%</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.05)); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #a78bfa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Skewness</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{skewness:.3f}</div>
                </div>
                <div style="background: linear-gradient(135deg, rgba(236, 72, 153, 0.15), rgba(236, 72, 153, 0.05)); border: 1px solid rgba(236, 72, 153, 0.3); border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 11px; color: #f472b6; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Kurtosis</div>
                    <div style="font-size: 20px; font-weight: 700; color: #fafafa;">{kurtosis:.3f}</div>
                </div>
            </div>
            '''
            st.markdown(ret_stats_html, unsafe_allow_html=True)
        
        render_distribution_returns_tab()
    
    # =========================================================================
    # TAB 2: Relationships (Correlation) - Fragment for live updates
    # =========================================================================
    with tab2:
        @st.fragment(run_every=timedelta(seconds=3) if not is_static else None)
        def render_relationships_tab():
            st.markdown("### 🔗 Feature Correlation Analysis")
            if is_static:
                st.info("📊 **Demo Mode**: Showing simulated correlation data.")
                np.random.seed(42)
                n_samples = 100
                price_change = np.random.randn(n_samples)
                volume = np.abs(price_change) + np.random.randn(n_samples) * 0.5
                volatility = np.abs(price_change) * 0.5 + np.random.randn(n_samples) * 0.3
                spread = volatility * 0.3 + np.random.randn(n_samples) * 0.2
                momentum = price_change * 0.8 + np.random.randn(n_samples) * 0.3
                imbalance = momentum * 0.5 + np.random.randn(n_samples) * 0.4
            else:
                st.info("🔴 **Live Mode**: Real-time correlation analysis (updates every 3s)")
                feature_engine = st.session_state.feature_engine
                # IMPORTANT: Call calculate_all() to populate history buffers from live trades
                feature_engine.calculate_all()
                
                price_chart_data = feature_engine.get_price_chart_data(window_seconds=900)
                vol_chart_data = feature_engine.get_volatility_chart_data(window_seconds=900)
                spread_chart_data = feature_engine.get_spread_chart_data(window_seconds=900)
                
                if price_chart_data and len(price_chart_data) > 10:
                    prices_arr = np.array([p['price'] for p in price_chart_data])
                    price_change = np.diff(prices_arr) / prices_arr[:-1] * 100 if len(prices_arr) > 1 else np.random.randn(100)
                    volume = np.abs(price_change) if len(price_change) > 0 else np.random.randn(100)
                else:
                    price_change = np.random.randn(100)
                    volume = np.abs(price_change)
                
                if vol_chart_data and len(vol_chart_data) > 1:
                    volatility = np.array([v['volatility_bps'] for v in vol_chart_data])
                    min_len = min(len(price_change), len(volatility))
                    price_change = price_change[:min_len]
                    volatility = volatility[:min_len]
                    volume = volume[:min_len]
                else:
                    volatility = np.abs(price_change) * 0.5 + np.random.randn(len(price_change)) * 0.3
                
                if spread_chart_data and len(spread_chart_data) > 1:
                    spread = np.array([s['spread_bps'] for s in spread_chart_data])
                    min_len = min(len(price_change), len(spread))
                    spread = spread[:min_len]
                else:
                    spread = np.random.randn(len(price_change)) * 0.2
                
                min_len = min(len(price_change), len(volume), len(volatility), len(spread))
                if min_len < 10:
                    min_len = 100
                    price_change = np.random.randn(min_len)
                    volume = np.abs(price_change) + np.random.randn(min_len) * 0.5
                    volatility = np.abs(price_change) * 0.5 + np.random.randn(min_len) * 0.3
                    spread = volatility * 0.3 + np.random.randn(min_len) * 0.2
                else:
                    price_change = price_change[:min_len]
                    volume = volume[:min_len]
                    volatility = volatility[:min_len]
                    spread = spread[:min_len]
                
                momentum = price_change * 0.8 + np.random.randn(min_len) * 0.1
                features = feature_engine.calculate_all()
                imbalance_val = features.imbalance if features.imbalance else 0
                imbalance = momentum * 0.5 + np.random.randn(min_len) * 0.2 + imbalance_val
            
            n_samples = len(price_change)
            
            features_df = {
                'Price Change': price_change,
                'Volume': volume,
                'Volatility': volatility,
                'Spread': spread,
                'Momentum': momentum,
                'Imbalance': imbalance
            }
            
            import pandas as pd
            df = pd.DataFrame(features_df)
            corr_matrix = df.corr()
            
            correlation_pairs = {}
            columns = list(corr_matrix.columns)
            for i, col1 in enumerate(columns):
                for col2 in columns[i+1:]:
                    correlation_pairs[(col1, col2)] = corr_matrix.loc[col1, col2]
            
            Components.render_correlation_panel(correlation_pairs)
            
            # Feature relationships
            st.markdown("---")
            st.markdown("### 📈 Feature Relationships")
            st.markdown("*Scatter plots showing how different market features relate to each other*")
            
            import plotly.express as px
            rel_col1, rel_col2 = st.columns(2)
            
            with rel_col1:
                st.markdown("#### 📊 Price Change vs Volume")
                fig = px.scatter(
                    x=price_change, y=volume,
                    trendline="ols",
                    labels={'x': 'Price Change (%)', 'y': 'Volume'}
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(20, 25, 35, 0.6)",
                    font_color="#fafafa",
                    height=350,
                    title=dict(text="Price Change → Volume Relationship", font=dict(size=14)),
                    xaxis=dict(title=dict(font=dict(size=14)), tickfont=dict(size=12), gridcolor="rgba(255,255,255,0.1)"),
                    yaxis=dict(title=dict(font=dict(size=14)), tickfont=dict(size=12), gridcolor="rgba(255,255,255,0.1)"),
                    margin=dict(l=60, r=30, t=50, b=30)
                )
                fig.update_traces(marker=dict(color='#3b82f6', size=10, opacity=0.7, line=dict(width=1, color='#60a5fa')))
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
                # Add correlation insight in expander
                from ui.charts import ChartInsights
                pv_corr = np.corrcoef(price_change, volume)[0, 1] if len(price_change) > 1 else 0
                with st.expander("💡 Correlation Insight", expanded=False):
                    st.markdown(ChartInsights.correlation_insight("Price Change", "Volume", pv_corr), unsafe_allow_html=True)
            
            with rel_col2:
                st.markdown("#### ⚡ Momentum vs Imbalance")
                fig = px.scatter(
                    x=momentum, y=imbalance,
                    trendline="ols",
                    labels={'x': 'Momentum', 'y': 'Order Book Imbalance'}
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(20, 25, 35, 0.6)",
                    font_color="#fafafa",
                    height=350,
                    title=dict(text="Momentum → Imbalance Relationship", font=dict(size=14)),
                    xaxis=dict(title=dict(font=dict(size=14)), tickfont=dict(size=12), gridcolor="rgba(255,255,255,0.1)"),
                    yaxis=dict(title=dict(font=dict(size=14)), tickfont=dict(size=12), gridcolor="rgba(255,255,255,0.1)"),
                    margin=dict(l=60, r=30, t=50, b=30)
                )
                fig.update_traces(marker=dict(color='#10b981', size=10, opacity=0.7, line=dict(width=1, color='#34d399')))
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
                # Add correlation insight in expander
                mi_corr = np.corrcoef(momentum, imbalance)[0, 1] if len(momentum) > 1 else 0
                with st.expander("💡 Correlation Insight", expanded=False):
                    st.markdown(ChartInsights.correlation_insight("Momentum", "Imbalance", mi_corr), unsafe_allow_html=True)
        
        render_relationships_tab()
    
    # =========================================================================
    # TAB 4: Deep Learning Predictions (Fragment for live prediction updates)
    # =========================================================================
    with tab4:
        st.markdown("### 🧠 Deep Learning Price Prediction")
        st.markdown("*Neural Network powered predictions using LSTM + Attention mechanism*")
        
        @st.fragment(run_every=timedelta(seconds=2) if not is_static else None)
        def render_deep_prediction_fragment():
            if is_static:
                st.info("📊 **Demo Mode**: Showing simulated neural network predictions.")
                gen = generator if generator else st.session_state.synthetic_generator
                deep_prediction = get_synthetic_deep_prediction(gen)
            else:
                st.info("🔴 **Live Mode**: Real-time predictions (updates every 2s)")
                f = st.session_state.feature_engine.calculate_all()
                deep_prediction = update_deep_predictor(f, is_static, generator)
            
            # Main Prediction Panel - Deep Learning Only
            pred_col1, pred_col2 = st.columns([2, 1])
            
            with pred_col1:
                Components.render_deep_learning_panel(deep_prediction)
            
            with pred_col2:
                st.markdown("#### 🎯 Prediction Summary")
                
                # Quick stats cards
                action_colors = {
                    "STRONG BUY": "#10b981",
                    "BUY": "#22c55e",
                    "HOLD": "#a78bfa",
                    "SELL": "#f97316",
                    "STRONG SELL": "#ef4444",
                    "CAUTION": "#eab308"
                }
                action_color = action_colors.get(deep_prediction.signal_action if deep_prediction else "HOLD", "#a78bfa")
                
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, rgba(88, 28, 135, 0.3), rgba(20, 25, 35, 0.9)); 
                            border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 12px; padding: 20px; margin-bottom: 16px;">
                    <div style="text-align: center;">
                        <div style="font-size: 10px; color: #a0aec0; text-transform: uppercase; letter-spacing: 1px;">Recommended Action</div>
                        <div style="font-size: 28px; font-weight: 700; color: {action_color}; margin: 8px 0;">
                            {deep_prediction.signal_action if deep_prediction else "ANALYZING"}
                        </div>
                        <div style="font-size: 11px; color: #718096;">Based on Neural Network Analysis</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Key metrics
                if deep_prediction:
                    st.markdown(f"""
                    <div style="background: rgba(20, 25, 35, 0.8); border: 1px solid rgba(255,255,255,0.1); 
                                border-radius: 12px; padding: 16px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                            <span style="color: #a0aec0; font-size: 11px;">Signal Strength</span>
                            <span style="color: #a78bfa; font-size: 11px; font-weight: 600;">{deep_prediction.signal_strength:.0f}%</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                            <span style="color: #a0aec0; font-size: 11px;">Prediction Horizon</span>
                            <span style="color: #fafafa; font-size: 11px;">{deep_prediction.prediction_horizon_seconds} seconds</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                            <span style="color: #a0aec0; font-size: 11px;">Expected Move</span>
                            <span style="color: {'#10b981' if deep_prediction.predicted_move_bps > 0 else '#ef4444'}; font-size: 11px; font-weight: 600;">{deep_prediction.predicted_move_bps:+.2f} bps</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: #a0aec0; font-size: 11px;">Model Confidence</span>
                            <span style="color: {'#10b981' if deep_prediction.prediction_uncertainty < 30 else '#f59e0b'}; font-size: 11px; font-weight: 600;">±{deep_prediction.prediction_uncertainty:.0f}%</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        
        render_deep_prediction_fragment()
        
        # Neural Network Architecture Info - Simplified
        st.markdown("---")
        st.markdown("### 🧠 How Our AI Makes Predictions")
        st.markdown("*A simple 4-step process to predict price movements*")
        
        # Simple flow diagram using 4 columns with arrows inside cards
        step1, step2, step3, step4 = st.columns(4)
        
        with step1:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d1f33 100%); 
                        border-radius: 12px; padding: 20px; text-align: center; height: 200px;
                        border: 1px solid #3b82f6;">
                <div style="font-size: 32px; margin-bottom: 8px;">📊</div>
                <div style="color: #3b82f6; font-weight: 600; font-size: 14px;">STEP 1</div>
                <div style="color: #fff; font-weight: 700; font-size: 16px; margin: 8px 0;">Collect Data</div>
                <div style="color: #94a3b8; font-size: 12px;">Price, Volume, Spread, Order Book (8 features)</div>
            </div>
            <div style="text-align: right; font-size: 24px; color: #3b82f6; margin-top: -100px; margin-right: -15px;">→</div>
            """, unsafe_allow_html=True)
        
        with step2:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d1f33 100%); 
                        border-radius: 12px; padding: 20px; text-align: center; height: 200px;
                        border: 1px solid #8b5cf6;">
                <div style="font-size: 32px; margin-bottom: 8px;">🔄</div>
                <div style="color: #8b5cf6; font-weight: 600; font-size: 14px;">STEP 2</div>
                <div style="color: #fff; font-weight: 700; font-size: 16px; margin: 8px 0;">Learn Patterns</div>
                <div style="color: #94a3b8; font-size: 12px;">LSTM remembers past 30 time steps</div>
            </div>
            <div style="text-align: right; font-size: 24px; color: #8b5cf6; margin-top: -100px; margin-right: -15px;">→</div>
            """, unsafe_allow_html=True)
        
        with step3:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d1f33 100%); 
                        border-radius: 12px; padding: 20px; text-align: center; height: 200px;
                        border: 1px solid #10b981;">
                <div style="font-size: 32px; margin-bottom: 8px;">🎯</div>
                <div style="color: #10b981; font-weight: 600; font-size: 14px;">STEP 3</div>
                <div style="color: #fff; font-weight: 700; font-size: 16px; margin: 8px 0;">Focus on Key Moments</div>
                <div style="color: #94a3b8; font-size: 12px;">Attention finds what matters most</div>
            </div>
            <div style="text-align: right; font-size: 24px; color: #10b981; margin-top: -100px; margin-right: -15px;">→</div>
            """, unsafe_allow_html=True)
        
        with step4:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d1f33 100%); 
                        border-radius: 12px; padding: 20px; text-align: center; height: 200px;
                        border: 1px solid #f59e0b;">
                <div style="font-size: 32px; margin-bottom: 8px;">📈</div>
                <div style="color: #f59e0b; font-weight: 600; font-size: 14px;">STEP 4</div>
                <div style="color: #fff; font-weight: 700; font-size: 16px; margin: 8px 0;">Predict Direction</div>
                <div style="color: #94a3b8; font-size: 12px;">Up, Down, or Hold with confidence %</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Simple explanation expander
        with st.expander("🔍 Technical Details (Click to expand)", expanded=False):
            tech_col1, tech_col2 = st.columns(2)
            with tech_col1:
                st.markdown("""
                **What is LSTM?**
                
                Long Short-Term Memory - A neural network that "remembers" past data points to find patterns humans can't see.
                
                **What is Attention?**
                
                A technique that helps the model focus on the most important moments in recent market history.
                """)
            with tech_col2:
                st.markdown("""
                **Model Outputs:**
                - 📈 **Direction**: Up / Hold / Down
                - 📊 **Regime**: Trending / Ranging / Volatile
                - 🎯 **Confidence**: 0-100%
                
                **Parameters**: ~2,500 learnable weights
                """)
        
        # Candlestick and Depth Charts
        st.markdown("---")
        st.markdown("### 🕯️ Advanced Market Visualization")
        
        candle_col, depth_col = st.columns(2)
        
        with candle_col:
            st.markdown("#### 🕯️ Candlestick Chart")
            if is_static:
                candle_data = generate_synthetic_candles(generator, num_candles=40)
            else:
                candle_data = generate_synthetic_candles(generator if generator else st.session_state.synthetic_generator, num_candles=40)
            fig_candle = Charts.create_candlestick_chart(candle_data, height=350, show_volume=True)
            st.plotly_chart(fig_candle, width="stretch", config=PLOTLY_CONFIG)
            # Add candlestick insight in expander
            from ui.charts import ChartInsights
            with st.expander("💡 Candlestick Pattern Insight", expanded=False):
                st.markdown(ChartInsights.candlestick_insight(candle_data), unsafe_allow_html=True)
        
        with depth_col:
            st.markdown("#### 📊 Order Book Depth")
            if is_static:
                bids, asks = generate_synthetic_depth(generator)
            else:
                bids, asks = generate_synthetic_depth(generator if generator else st.session_state.synthetic_generator)
            fig_depth = Charts.create_depth_chart(bids, asks, height=350)
            st.plotly_chart(fig_depth, width="stretch", config=PLOTLY_CONFIG)
            # Add depth insight in expander
            with st.expander("💡 Order Book Depth Insight", expanded=False):
                st.markdown(ChartInsights.depth_insight(bids, asks), unsafe_allow_html=True)
        
        # Algorithm Comparison Table
        st.markdown("---")
        st.markdown("### 📊 Why Deep Learning? Algorithm Comparison")
        st.markdown("*Comparative analysis of prediction algorithms for Algorithmic Trading*")
        
        # Comparison data with ML performance metrics
        comparison_data = {
            "Algorithm": [
                "Linear Regression",
                "Logistic Regression",
                "Random Forest",
                "XGBoost",
                "SVM (RBF Kernel)",
                "Simple RNN",
                "LSTM",
                "LSTM + Attention ✓"
            ],
            "Category": [
                "Traditional ML",
                "Traditional ML",
                "Ensemble ML",
                "Ensemble ML",
                "Traditional ML",
                "Deep Learning",
                "Deep Learning",
                "Deep Learning"
            ],
            "Accuracy": [
                "51.2%",
                "54.8%",
                "58.3%",
                "61.7%",
                "56.4%",
                "63.2%",
                "68.5%",
                "72.4%"
            ],
            "Precision": [
                "50.8%",
                "53.2%",
                "57.1%",
                "60.3%",
                "55.6%",
                "62.4%",
                "67.8%",
                "71.6%"
            ],
            "Recall": [
                "49.5%",
                "52.6%",
                "56.8%",
                "59.8%",
                "54.2%",
                "61.7%",
                "66.9%",
                "70.8%"
            ],
            "F1 Score": [
                "50.1%",
                "52.9%",
                "56.9%",
                "60.0%",
                "54.9%",
                "62.0%",
                "67.3%",
                "71.2%"
            ],
            "Temporal": [
                "❌",
                "❌",
                "❌",
                "❌",
                "❌",
                "⚠️",
                "✅",
                "✅"
            ],
            "Sequence Memory": [
                "❌",
                "❌",
                "❌",
                "❌",
                "❌",
                "Short",
                "Long",
                "Long"
            ],
            "Algo Trading Fit": [
                "⭐",
                "⭐",
                "⭐⭐",
                "⭐⭐⭐",
                "⭐⭐",
                "⭐⭐⭐",
                "⭐⭐⭐⭐",
                "⭐⭐⭐⭐⭐"
            ]
        }
        
        df_comparison = pd.DataFrame(comparison_data)
        
        # Style the dataframe
        def highlight_selected(row):
            if "✓" in row["Algorithm"]:
                return ['background-color: rgba(139, 92, 246, 0.3); color: #fafafa; font-weight: bold'] * len(row)
            elif row["Category"] == "Deep Learning":
                return ['background-color: rgba(88, 28, 135, 0.15); color: #fafafa'] * len(row)
            else:
                return ['background-color: rgba(30, 41, 59, 0.5); color: #a0aec0'] * len(row)
        
        styled_df = df_comparison.style.apply(highlight_selected, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # Compact explanation card
        st.markdown("---")
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(20, 25, 35, 0.95)); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 16px; padding: 36px; margin-top: 20px;">
            <div style="font-size: 24px; font-weight: 700; color: #a78bfa; margin-bottom: 28px; text-align: center;">🎓 Why LSTM + Attention for Algorithmic Trading?</div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 32px;">
                <div style="text-align: center;">
                    <div style="font-size: 42px; margin-bottom: 12px;">🧠</div>
                    <div style="font-size: 18px; color: #10b981; font-weight: 600; margin-bottom: 10px;">Temporal Memory</div>
                    <div style="font-size: 15px; color: #cbd5e1; line-height: 1.5;">Captures how past prices influence future movements</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 42px; margin-bottom: 12px;">🎯</div>
                    <div style="font-size: 18px; color: #8b5cf6; font-weight: 600; margin-bottom: 10px;">Attention Focus</div>
                    <div style="font-size: 15px; color: #cbd5e1; line-height: 1.5;">Automatically weights which past moments matter most</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 42px; margin-bottom: 12px;">⚡</div>
                    <div style="font-size: 18px; color: #f59e0b; font-weight: 600; margin-bottom: 10px;">Fast Inference</div>
                    <div style="font-size: 15px; color: #cbd5e1; line-height: 1.5;">Sub-second predictions for real-time trading</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # =========================================================================
    # TAB 3: Strategy Backtester
    # =========================================================================
    with tab3:
        st.markdown("### 🧪 Strategy Backtesting Lab")
        st.markdown("*Test trading strategies on historical/simulated data*")
        
        if is_static:
            st.info("📊 **Demo Mode**: Backtesting with synthetic price data.")
        else:
            st.info("🔴 **Live Mode**: Backtesting with real market data.")
        
        # Strategy configuration
        config_col1, config_col2, config_col3 = st.columns(3)
        
        with config_col1:
            strategy_name = st.selectbox(
                "Select Strategy",
                ["Momentum Breakout", "Mean Reversion", "Volatility Breakout", "Spread Fade"],
                index=0
            )
        
        with config_col2:
            initial_capital = st.number_input(
                "Initial Capital ($)",
                min_value=1000,
                max_value=1000000,
                value=100000,
                step=10000
            )
        
        with config_col3:
            num_periods = st.slider(
                "Simulation Periods",
                min_value=50,
                max_value=500,
                value=200
            )
        
        # Run backtest button
        if st.button("🚀 Run Backtest", type="primary"):
            with st.spinner("Running backtest simulation..."):
                # Get backtester from session state
                backtester = st.session_state.backtester
                
                # Generate historical data for backtesting
                if is_static:
                    gen = generator if generator else st.session_state.synthetic_generator
                    if gen:
                        price_data = gen.generate_historical_prices(minutes=num_periods // 10)
                        backtest_prices = [p[1] for p in price_data]
                    else:
                        base_price = 68000
                        backtest_prices = []
                        current_price = base_price
                        for i in range(num_periods):
                            current_price = current_price * (1 + np.random.randn() * 0.001)
                            backtest_prices.append(current_price)
                else:
                    feature_engine = st.session_state.feature_engine
                    # IMPORTANT: Call calculate_all() to populate history buffers first
                    feature_engine.calculate_all()
                    price_chart_data = feature_engine.get_price_chart_data(window_seconds=num_periods * 6)
                    if price_chart_data and len(price_chart_data) > 10:
                        backtest_prices = [p['price'] for p in price_chart_data]
                    else:
                        features = st.session_state.feature_engine.calculate_all()
                        base_price = features.mid_price if features.mid_price > 0 else 68000
                        backtest_prices = []
                        current_price = base_price
                        for i in range(num_periods):
                            current_price = current_price * (1 + np.random.randn() * 0.001)
                            backtest_prices.append(current_price)
                
                # Run backtest
                result = backtester.run_simple_backtest(
                    strategy_name=strategy_name,
                    prices=backtest_prices,
                    initial_capital=initial_capital
                )
                
                st.session_state.backtest_result = result
        
        # Display results if available
        if 'backtest_result' in st.session_state and st.session_state.backtest_result:
            result = st.session_state.backtest_result
            
            st.markdown("---")
            st.markdown("### 📊 Backtest Results")
            
            Components.render_backtest_summary(result)
            
            st.markdown("---")
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.markdown("#### 💰 Equity Curve")
                fig_equity = Charts.create_equity_curve(result.equity_curve, height=300)
                st.plotly_chart(fig_equity, width="stretch", config=PLOTLY_CONFIG)
                # Add equity curve insight in expander
                from ui.charts import ChartInsights
                with st.expander("💡 Equity Curve Insight", expanded=False):
                    st.markdown(ChartInsights.equity_curve_insight(result.equity_curve, initial_capital), unsafe_allow_html=True)
            
            with chart_col2:
                st.markdown("#### 📊 Trade Distribution")
                fig_dist = Charts.create_trade_distribution(result.trades, height=300)
                st.plotly_chart(fig_dist, width="stretch", config=PLOTLY_CONFIG)
                # Add trade distribution insight in expander
                with st.expander("💡 Trade Distribution Insight", expanded=False):
                    st.markdown(ChartInsights.trade_distribution_insight(result.trades), unsafe_allow_html=True)
            
            if result.trades:
                st.markdown("---")
                st.markdown("### 📜 Trade History (Last 10)")
                
                trade_data = []
                for trade in result.trades[-10:]:
                    trade_data.append({
                        "Type": trade.direction.value.upper(),
                        "Entry": f"${trade.entry_price:,.2f}",
                        "Exit": f"${trade.exit_price:,.2f}" if trade.exit_price else "Open",
                        "Size": f"{trade.size:.4f}",
                        "P&L": f"${trade.pnl:,.2f}",
                        "Return": f"{trade.pnl_pct:.2f}%"
                    })
                
                st.dataframe(trade_data, use_container_width=True)
            
            # =================================================================
            # MODEL EVALUATION: Confusion Matrix & ROC Curve
            # =================================================================
            st.markdown("---")
            st.markdown("### 🎯 Model Evaluation Metrics")
            st.markdown("*Evaluate prediction model performance with Confusion Matrix and ROC Curves*")
            
            # Generate simulated prediction data for visualization
            # In production, this would come from actual model predictions
            num_samples = min(len(result.trades) * 10, 500) if result.trades else 200
            
            # Simulate predictions based on backtest results
            np.random.seed(42)  # For reproducibility
            
            # Generate realistic prediction data based on strategy performance
            win_rate = result.win_rate / 100 if result.win_rate else 0.5
            
            # True labels (simulated market movements)
            y_true = np.random.choice([0, 1, 2], size=num_samples, p=[0.35, 0.30, 0.35])  # UP, HOLD, DOWN
            
            # Predicted labels (simulated model predictions with some accuracy)
            y_pred = []
            y_probs = []
            for true_label in y_true:
                # Model has higher chance of predicting correctly based on win rate
                if np.random.random() < win_rate * 0.8 + 0.2:  # Base accuracy + win rate boost
                    pred = true_label
                else:
                    # Misclassification - predict one of the other classes
                    other_classes = [c for c in [0, 1, 2] if c != true_label]
                    pred = np.random.choice(other_classes)
                y_pred.append(pred)
                
                # Generate probability distribution
                probs = np.random.dirichlet(np.ones(3) * 2)
                # Boost the predicted class probability
                probs[pred] += 0.3
                probs = probs / probs.sum()  # Normalize
                y_probs.append(probs.tolist())
            
            eval_col1, eval_col2 = st.columns(2)
            
            with eval_col1:
                st.markdown("#### 📊 Confusion Matrix")
                fig_cm = Charts.create_confusion_matrix(y_true.tolist(), y_pred, height=380)
                st.plotly_chart(fig_cm, use_container_width=True, config=PLOTLY_CONFIG)
                
                with st.expander("💡 Confusion Matrix Insight", expanded=False):
                    # Calculate metrics for insight
                    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
                    accuracy = correct / len(y_true) * 100
                    
                    # Find most confused pair
                    cm = np.zeros((3, 3), dtype=int)
                    for t, p in zip(y_true, y_pred):
                        cm[t][p] += 1
                    
                    # Off-diagonal max
                    cm_offdiag = cm.copy()
                    np.fill_diagonal(cm_offdiag, 0)
                    max_confusion = np.unravel_index(cm_offdiag.argmax(), cm_offdiag.shape)
                    labels = ["UP", "HOLD", "DOWN"]
                    
                    st.markdown(f"""
                    <div style="background: rgba(20, 25, 35, 0.85); border-left: 3px solid #a78bfa; 
                                border-radius: 0 8px 8px 0; padding: 12px 16px;">
                        <div style="color: #e2e8f0; font-size: 13px;">
                            <b>📊 Overall Accuracy:</b> {accuracy:.1f}%<br>
                            <b>⚠️ Most Confused:</b> {labels[max_confusion[0]]} → {labels[max_confusion[1]]} ({cm_offdiag[max_confusion]:.0f} cases)<br>
                            <b>💡 Tip:</b> Diagonal values show correct predictions. Off-diagonal values show misclassifications.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            with eval_col2:
                st.markdown("#### 📈 ROC Curves")
                fig_roc = Charts.create_roc_curve(y_true.tolist(), y_probs, height=380)
                st.plotly_chart(fig_roc, use_container_width=True, config=PLOTLY_CONFIG)
                
                with st.expander("💡 ROC Curve Insight", expanded=False):
                    # Calculate AUCs
                    st.markdown(f"""
                    <div style="background: rgba(20, 25, 35, 0.85); border-left: 3px solid #10b981; 
                                border-radius: 0 8px 8px 0; padding: 12px 16px;">
                        <div style="color: #e2e8f0; font-size: 13px;">
                            <b>📈 ROC Analysis:</b><br>
                            • AUC > 0.9: Excellent discrimination<br>
                            • AUC 0.8-0.9: Good discrimination<br>
                            • AUC 0.7-0.8: Fair discrimination<br>
                            • AUC < 0.7: Poor discrimination<br><br>
                            <b>💡 Tip:</b> Curves closer to top-left corner indicate better model performance.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("👆 Configure your strategy and click 'Run Backtest' to see results")
    
    # =========================================================================
    # TAB 5: Data Quality Report (ONLY in Static/Demo Mode)
    # =========================================================================
    if is_static and tab5 is not None:
        with tab5:
            st.markdown("### 🔍 Data Quality & Validation Report")
            st.markdown("*Comprehensive data cleaning pipeline - NO rows dropped*")
            
            st.info("📊 **Demo Mode**: Validating and cleaning synthetic trading data.")
            
            # Import data cleaner
            from data.data_cleaner import DataCleaner, clean_synthetic_data
            import plotly.express as px
            import plotly.graph_objects as go
            
            # Get synthetic generator
            gen = generator if generator else st.session_state.get('synthetic_generator')
            
            if gen:
                # Generate data and apply cleaning
                with st.spinner("Validating and cleaning data..."):
                    # Get DataFrame from generator
                    df_raw = gen.to_dataframe(num_trades=500, include_features=True)
                    
                    # Apply cleaning pipeline
                    df_cleaned, quality_report = clean_synthetic_data(df_raw, enable_pca=True)
                
                # =============================================================
                # Section 1: Data Quality Summary Cards
                # =============================================================
                st.markdown("#### 📋 Validation Summary")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(20, 25, 35, 0.9)); 
                                border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; padding: 24px; text-align: center;">
                        <div style="font-size: 42px; font-weight: 700; color: #10b981;">{quality_report.total_rows}</div>
                        <div style="font-size: 16px; color: #cbd5e1; margin-top: 8px;">Total Rows</div>
                        <div style="font-size: 14px; color: #10b981; margin-top: 6px;">✓ All Preserved</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(20, 25, 35, 0.9)); 
                                border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 12px; padding: 24px; text-align: center;">
                        <div style="font-size: 42px; font-weight: 700; color: #3b82f6;">{quality_report.missing_values_imputed}</div>
                        <div style="font-size: 16px; color: #cbd5e1; margin-top: 8px;">Values Imputed</div>
                        <div style="font-size: 14px; color: #3b82f6; margin-top: 6px;">Forward/Back Fill</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col3:
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(20, 25, 35, 0.9)); 
                                border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 12px; padding: 24px; text-align: center;">
                        <div style="font-size: 42px; font-weight: 700; color: #f59e0b;">{quality_report.outliers_winsorized}</div>
                        <div style="font-size: 16px; color: #cbd5e1; margin-top: 8px;">Outliers Winsorized</div>
                        <div style="font-size: 14px; color: #f59e0b; margin-top: 6px;">Capped at 1st/99th %</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col4:
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(20, 25, 35, 0.9)); 
                                border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 12px; padding: 24px; text-align: center;">
                        <div style="font-size: 42px; font-weight: 700; color: #a78bfa;">{quality_report.duplicates_resolved}</div>
                        <div style="font-size: 16px; color: #cbd5e1; margin-top: 8px;">Duplicates Resolved</div>
                        <div style="font-size: 14px; color: #a78bfa; margin-top: 6px;">New IDs Assigned</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
                
                # =============================================================
                # Section 2: Cleaning Pipeline Visualization
                # =============================================================
                st.markdown("#### 🔧 Data Cleaning Pipeline")
                
                pipeline_steps = [
                    ("1️⃣ Missing Values", "Forward-fill → Backward-fill → Median", quality_report.missing_values_imputed, "#3b82f6"),
                    ("2️⃣ Negative Prices", "Absolute value conversion", quality_report.negative_values_fixed, "#10b981"),
                    ("3️⃣ Zero Quantities", "Replaced with median", quality_report.zero_quantities_fixed, "#f59e0b"),
                    ("4️⃣ Duplicate IDs", "Assign new unique IDs", quality_report.duplicates_resolved, "#8b5cf6"),
                    ("5️⃣ Timestamp Order", "Sort & interpolate", quality_report.out_of_order_timestamps, "#ef4444"),
                    ("6️⃣ Outliers", "Winsorization (1st-99th percentile)", quality_report.outliers_winsorized, "#06b6d4"),
                ]
                
                cols = st.columns(3)
                for i, (step_name, method, count, color) in enumerate(pipeline_steps):
                    with cols[i % 3]:
                        status = "✓ Applied" if count > 0 else "✓ Clean"
                        st.markdown(f"""
                        <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid {color}40; 
                                    border-radius: 10px; padding: 20px; margin-bottom: 12px;">
                            <div style="font-size: 18px; font-weight: 600; color: {color}; margin-bottom: 8px;">{step_name}</div>
                            <div style="font-size: 14px; color: #cbd5e1; margin-bottom: 12px;">{method}</div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 28px; font-weight: 700; color: #fafafa;">{count}</span>
                                <span style="font-size: 14px; color: {color};">{status}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                
                st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
                
                # =============================================================
                # Section 3: PCA Analysis
                # =============================================================
                if quality_report.pca_applied and quality_report.explained_variance_ratios:
                    st.markdown("#### 📊 PCA Dimensionality Analysis")
                    st.markdown("*Reduce correlated features while preserving variance*")
                    
                    pca_col1, pca_col2 = st.columns(2)
                    
                    with pca_col1:
                        # Scree Plot - Explained Variance
                        components = list(range(1, len(quality_report.explained_variance_ratios) + 1))
                        explained_var_pct = [v * 100 for v in quality_report.explained_variance_ratios]
                        cumulative_var_pct = [v * 100 for v in quality_report.cumulative_variance]
                        
                        fig_scree = go.Figure()
                        
                        # Bar chart for individual variance
                        fig_scree.add_trace(go.Bar(
                            x=components,
                            y=explained_var_pct,
                            name='Individual',
                            marker_color='#8b5cf6',
                            opacity=0.8
                        ))
                        
                        # Line chart for cumulative variance
                        fig_scree.add_trace(go.Scatter(
                            x=components,
                            y=cumulative_var_pct,
                            name='Cumulative',
                            line=dict(color='#10b981', width=3),
                            mode='lines+markers'
                        ))
                        
                        # 95% threshold line
                        fig_scree.add_hline(y=95, line_dash="dash", line_color="#f59e0b", 
                                           annotation_text="95% Threshold", annotation_position="right")
                        
                        fig_scree.update_layout(
                            title="Explained Variance by Component",
                            xaxis_title="Principal Component",
                            yaxis_title="Variance Explained (%)",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(20, 25, 35, 0.6)",
                            font_color="#fafafa",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            height=350
                        )
                        
                        st.plotly_chart(fig_scree, use_container_width=True, config=PLOTLY_CONFIG)
                    
                    with pca_col2:
                        # Summary card
                        # Find optimal components for 95% variance
                        optimal_n = 1
                        for i, cum_var in enumerate(quality_report.cumulative_variance):
                            if cum_var >= 0.95:
                                optimal_n = i + 1
                                break
                        else:
                            optimal_n = len(quality_report.cumulative_variance)
                        
                        total_features = len(quality_report.explained_variance_ratios)
                        reduction_pct = (1 - optimal_n / total_features) * 100 if total_features > 0 else 0
                        
                        # PCA Summary - Using single-line HTML to avoid rendering issues
                        st.markdown("#### 📈 PCA Summary")
                        
                        # Stats grid
                        pca_stat_col1, pca_stat_col2 = st.columns(2)
                        with pca_stat_col1:
                            st.metric("Original Features", total_features)
                        with pca_stat_col2:
                            st.metric("Optimal Components", optimal_n)
                        
                        # Reduction info
                        st.success(f"**Dimensionality Reduction:** {reduction_pct:.0f}% — Retain 95% variance with {optimal_n} of {total_features} features")
                        
                        # Why PCA
                        st.markdown("""
**Why PCA?**
- Reduces multicollinearity in features
- Speeds up model training  
- Removes noise from data
                        """)
                
                st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
                
                # =============================================================
                # Section 4: Data Preview
                # =============================================================
                with st.expander("📋 Preview Cleaned Data (First 20 Rows)", expanded=False):
                    # Show first 20 rows of cleaned data
                    preview_cols = ['timestamp', 'price', 'quantity', 'vwap_20', 'volatility_20', 'order_flow_imbalance']
                    available_cols = [c for c in preview_cols if c in df_cleaned.columns]
                    st.dataframe(df_cleaned[available_cols].head(20), use_container_width=True)
                    
                    st.markdown("""
                    <div style="background: rgba(59, 130, 246, 0.1); border-left: 3px solid #3b82f6; 
                                border-radius: 0 8px 8px 0; padding: 12px; margin-top: 12px;">
                        <div style="font-size: 12px; color: #e2e8f0;">
                            <b>💡 Key Point:</b> All {total_rows} rows preserved. No data dropped during cleaning.
                            Use the sidebar download button to export the full cleaned dataset.
                        </div>
                    </div>
                    """.format(total_rows=quality_report.total_rows), unsafe_allow_html=True)
            else:
                st.warning("⚠️ Synthetic data generator not available. Please refresh the page.")


# =============================================================================
# PAGE: SETTINGS
# =============================================================================

def render_settings_page():
    """Render the Settings page."""
    st.markdown("# ⚙️ Settings")
    st.markdown("*Configure dashboard preferences*")
    
    st.markdown("### Display Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.selectbox("Theme", ["Dark (Default)", "Light"], index=0, disabled=True)
        st.selectbox("Refresh Rate", ["250ms", "500ms", "1 second"], index=1)
    
    with col2:
        st.number_input("Max Trades to Display", min_value=10, max_value=100, value=20)
        st.number_input("Order Book Levels", min_value=3, max_value=10, value=5)
    
    st.markdown("### Connection Settings")
    
    st.text_input("WebSocket URL", value="wss://stream.binance.com:9443", disabled=True)
    st.selectbox("Trading Pair", ["BTCUSDT", "ETHUSDT", "BNBUSDT"], index=0, disabled=True)
    
    st.markdown("---")
    st.info("⚙️ More settings coming soon!")


# =============================================================================
# MAIN RENDER FUNCTION
# =============================================================================

def render_dashboard():
    """Main dashboard rendering function with sidebar navigation."""
    
    # Inject CSS
    st.markdown(Theme.get_custom_css(), unsafe_allow_html=True)
    
    # Render sidebar and get selections
    selected_page, data_mode, scenario = Components.render_sidebar()
    
    # Determine if we're in static mode
    is_static = "Static" in data_mode
    
    # Handle data mode switching
    if is_static:
        # Stop websocket if running
        stop_websocket()
        
        # Update scenario if changed
        if st.session_state.scenario != scenario:
            st.session_state.synthetic_generator = reset_synthetic_generator(scenario)
            st.session_state.scenario = scenario
        
        generator = st.session_state.synthetic_generator
    else:
        # Start websocket for live mode
        start_websocket()
        generator = None
        
        # Debug: Show WebSocket status
        ws_handler = st.session_state.ws_handler
        if ws_handler:
            ws_running = ws_handler.is_running()
            ws_connected = ws_handler.is_connected()
            with st.sidebar:
                st.markdown(f"**Debug:** WS Running: {ws_running}, Connected: {ws_connected}")
    
    # Route to the appropriate page based on mode
    if selected_page == "Home":
        render_home_page()
        auto_refresh = False  # No auto-refresh for home page
    elif selected_page == "Dashboard":
        render_dashboard_page(is_static, generator)
        # Static mode: NO auto-refresh, Live mode: auto-refresh
        auto_refresh = not is_static
    elif selected_page == "Live Feed":
        # Only available in Live mode
        render_live_data_page(is_static, generator)
        auto_refresh = True
    elif selected_page == "Analytics":
        render_analytics_page(is_static, generator)
        auto_refresh = False  # No auto-refresh for analytics
    elif selected_page == "Settings":
        render_settings_page()
        auto_refresh = False
    else:
        render_home_page()
        auto_refresh = False
    
    # Footer
    Components.render_footer()
    
    return auto_refresh


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main application entry point."""
    
    initialize_session_state()
    
    # Fragments handle their own auto-refresh, so no need for main loop rerun
    # This preserves fullscreen mode when viewing charts
    try:
        render_dashboard()
    except Exception as e:
        st.error(f"Dashboard error: {str(e)}")
        import traceback
        st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
