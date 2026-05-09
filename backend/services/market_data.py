"""
AlgoViz Backend — Market Data Service
=======================================

Manages exchange WebSocket connections, feature calculation,
and data pipeline from exchanges to frontend clients.

Migrated and enhanced from the original src/data/ and src/features/ modules.
"""

import asyncio
import json
import logging
import time
import math
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Deque
from collections import deque
from dataclasses import dataclass, field

import websockets

from config import settings
from ws.hub import (
    broadcast_market_update,
    broadcast_trade,
    broadcast_insight,
    broadcast_prediction,
    broadcast_alert,
)
from services.ml_engine import ml_engine

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═════════════════════════════════════════════════════════════════════

@dataclass
class Trade:
    timestamp: datetime
    price: float
    quantity: float
    is_buyer_maker: bool
    trade_id: int


@dataclass
class DepthSnapshot:
    bids: List[tuple]  # [(price, qty), ...]
    asks: List[tuple]
    best_bid: float
    best_ask: float
    bid_volume: float
    ask_volume: float
    timestamp: datetime


@dataclass
class Features:
    """Calculated market features — the core data packet."""
    symbol: str = "BTCUSDT"
    current_price: float = 0.0
    mid_price: float = 0.0
    spread: float = 0.0
    spread_bps: float = 0.0
    vwap: float = 0.0
    twap: float = 0.0
    imbalance: float = 0.0
    imbalance_pct: float = 0.0
    volatility_bps: float = 0.0
    velocity: float = 0.0
    velocity_baseline: float = 20.0
    buy_pressure: float = 0.5
    price_change: float = 0.0
    price_change_pct: float = 0.0
    price_vs_vwap: float = 0.0
    price_vs_twap: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    timestamp: Optional[datetime] = None

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        if d.get("timestamp"):
            d["timestamp"] = d["timestamp"].isoformat()
        return d


# ═════════════════════════════════════════════════════════════════════
# MARKET DATA SERVICE (Singleton)
# ═════════════════════════════════════════════════════════════════════

class MarketDataService:
    """
    Central hub for market data ingestion, feature calculation,
    and broadcasting to WebSocket clients.
    """

    def __init__(self):
        # ── Buffers ──
        self._trades: Deque[Trade] = deque(maxlen=settings.TRADES_BUFFER_SIZE)
        self._depth: Deque[DepthSnapshot] = deque(maxlen=settings.DEPTH_BUFFER_SIZE)
        self._price_history: Deque[dict] = deque(maxlen=settings.PRICE_HISTORY_SIZE)
        self._spread_history: Deque[dict] = deque(maxlen=settings.SPREAD_HISTORY_SIZE)
        self._volatility_history: Deque[dict] = deque(maxlen=settings.VOLATILITY_HISTORY_SIZE)

        # ── Connection state ──
        self._connected = False
        self._status = "disconnected"
        self._running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._broadcast_task: Optional[asyncio.Task] = None

        # ── Feature tracking ──
        self._current_features = Features()
        self._initial_price: Optional[float] = None
        self._velocity_baseline = settings.DEFAULT_VELOCITY_BASELINE
        self._last_spread_sample = 0.0

        # ── Stats ──
        self._trade_count = 0
        self._start_time = datetime.utcnow()
        self._last_update: Optional[datetime] = None

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self):
        """Start the market data service."""
        if self._running:
            return
        self._running = True
        self._start_time = datetime.utcnow()
        self._ws_task = asyncio.create_task(self._connection_loop())
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info("Market data service started")

    async def stop(self):
        """Stop the market data service."""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._broadcast_task:
            self._broadcast_task.cancel()
        self._connected = False
        self._status = "disconnected"
        logger.info("Market data service stopped")

    # ── WebSocket Connection ──────────────────────────────────────

    async def _connection_loop(self):
        """Main connection loop with auto-reconnect."""
        attempt = 0
        max_attempts = 10

        while self._running:
            try:
                self._status = "connecting"
                async with websockets.connect(
                    settings.BINANCE_COMBINED_WS,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._connected = True
                    self._status = "connected"
                    attempt = 0
                    logger.info("Connected to Binance WebSocket")

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        await self._process_message(raw_msg)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed")
            except Exception as e:
                err_str = str(e)
                # Detect geo-restriction (HTTP 451) — works across all websockets versions
                if "451" in err_str:
                    logger.warning(
                        "Binance WebSocket blocked (HTTP 451 — geo-restriction). "
                        "The backend will continue serving API requests without live data. "
                        "Retrying in 5 minutes..."
                    )
                    self._status = "geo_blocked"
                    self._connected = False
                    await asyncio.sleep(300)
                    continue
                logger.error(f"WebSocket error: {e}")

            self._connected = False
            self._status = "reconnecting"
            attempt += 1

            if attempt >= max_attempts:
                logger.warning("Max reconnection attempts reached, backing off 60s")
                self._status = "failed"
                await asyncio.sleep(60)
                attempt = 0
            else:
                delay = min(2 ** attempt, 30)
                logger.info(f"Reconnecting in {delay}s (attempt {attempt})")
                await asyncio.sleep(delay)

    # ── Message Processing ────────────────────────────────────────

    async def _process_message(self, raw: str):
        """Process a raw WebSocket message from Binance."""
        try:
            msg = json.loads(raw)
            data = msg.get("data", msg)
            stream = msg.get("stream", "")

            if "trade" in stream or data.get("e") == "trade":
                self._process_trade(data)
            elif "depth" in stream or "bids" in data:
                self._process_depth(data)

            self._last_update = datetime.utcnow()
        except Exception as e:
            logger.debug(f"Message parse error: {e}")

    def _process_trade(self, data: dict):
        """Parse and buffer a trade message."""
        try:
            trade = Trade(
                timestamp=datetime.utcfromtimestamp(data["T"] / 1000),
                price=float(data["p"]),
                quantity=float(data["q"]),
                is_buyer_maker=data["m"],
                trade_id=data["t"],
            )
            self._trades.append(trade)
            self._trade_count += 1

            if self._initial_price is None:
                self._initial_price = trade.price
        except (KeyError, ValueError) as e:
            logger.debug(f"Trade parse error: {e}")

    def _process_depth(self, data: dict):
        """Parse and buffer a depth snapshot."""
        try:
            bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
            asks = [(float(p), float(q)) for p, q in data.get("asks", [])]

            if not bids or not asks:
                return

            snap = DepthSnapshot(
                bids=bids,
                asks=asks,
                best_bid=bids[0][0],
                best_ask=asks[0][0],
                bid_volume=sum(q for _, q in bids),
                ask_volume=sum(q for _, q in asks),
                timestamp=datetime.utcnow(),
            )
            self._depth.append(snap)
        except (IndexError, ValueError) as e:
            logger.debug(f"Depth parse error: {e}")

    # ── Feature Calculation ───────────────────────────────────────

    def calculate_features(self) -> Features:
        """Calculate all trading features from current buffer state."""
        now = datetime.utcnow()
        f = Features(symbol=settings.DEFAULT_SYMBOL, timestamp=now)

        # Latest depth
        depth = self._depth[-1] if self._depth else None
        if depth:
            f.best_bid = depth.best_bid
            f.best_ask = depth.best_ask
            f.bid_volume = depth.bid_volume
            f.ask_volume = depth.ask_volume
            f.mid_price = (depth.best_bid + depth.best_ask) / 2
            f.spread = depth.best_ask - depth.best_bid
            f.spread_bps = (f.spread / f.mid_price * 10000) if f.mid_price else 0.0

            total_vol = depth.bid_volume + depth.ask_volume
            f.imbalance = (
                (depth.bid_volume - depth.ask_volume) / total_vol
                if total_vol > 0 else 0.0
            )
            f.imbalance_pct = f.imbalance * 100

        # Current price
        if self._trades:
            f.current_price = self._trades[-1].price

        # Price change
        if self._initial_price and self._initial_price > 0:
            f.price_change = f.current_price - self._initial_price
            f.price_change_pct = (f.price_change / self._initial_price) * 100

        # VWAP
        f.vwap = self._calc_vwap(now)

        # TWAP
        f.twap = self._calc_twap(now)

        # Price vs benchmarks
        if f.vwap > 0:
            f.price_vs_vwap = ((f.current_price - f.vwap) / f.vwap) * 100
        if f.twap > 0:
            f.price_vs_twap = ((f.current_price - f.twap) / f.twap) * 100

        # Velocity
        f.velocity = self._calc_velocity(now)
        f.velocity_baseline = self._velocity_baseline

        # Buy Pressure
        f.buy_pressure = self._calc_buy_pressure(now)

        # Volatility
        f.volatility_bps = self._calc_volatility(now)

        self._current_features = f
        self._update_history(f)
        return f

    def _calc_vwap(self, now: datetime) -> float:
        cutoff = now - timedelta(seconds=settings.VWAP_WINDOW)
        trades = [t for t in self._trades if t.timestamp >= cutoff]
        if not trades:
            return self._trades[-1].price if self._trades else 0.0
        total_pq = sum(t.price * t.quantity for t in trades)
        total_q = sum(t.quantity for t in trades)
        return total_pq / total_q if total_q > 0 else 0.0

    def _calc_twap(self, now: datetime) -> float:
        cutoff = now - timedelta(seconds=settings.VWAP_WINDOW)
        trades = [t for t in self._trades if t.timestamp >= cutoff]
        if not trades:
            return self._trades[-1].price if self._trades else 0.0
        return sum(t.price for t in trades) / len(trades)

    def _calc_velocity(self, now: datetime) -> float:
        cutoff = now - timedelta(seconds=settings.VELOCITY_WINDOW)
        count = sum(1 for t in self._trades if t.timestamp >= cutoff)
        return count / max(settings.VELOCITY_WINDOW, 1)

    def _calc_buy_pressure(self, now: datetime) -> float:
        cutoff = now - timedelta(seconds=settings.BUY_PRESSURE_WINDOW)
        trades = [t for t in self._trades if t.timestamp >= cutoff]
        if not trades:
            return 0.5
        buy_vol = sum(t.quantity for t in trades if not t.is_buyer_maker)
        total_vol = sum(t.quantity for t in trades)
        return buy_vol / total_vol if total_vol > 0 else 0.5

    def _calc_volatility(self, now: datetime) -> float:
        cutoff = now - timedelta(seconds=settings.VOLATILITY_WINDOW)
        prices = [t.price for t in self._trades if t.timestamp >= cutoff]
        if len(prices) < 2:
            return 0.0
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        if not returns:
            return 0.0
        return float(np.std(returns) * 10000)

    def _update_history(self, f: Features):
        """Append feature snapshot to chart data histories."""
        now = f.timestamp or datetime.utcnow()
        self._price_history.append({
            "timestamp": now.isoformat(),
            "price": f.current_price,
            "vwap": f.vwap,
            "twap": f.twap,
        })
        # Sample spread every 5 seconds
        current_time = time.time()
        if current_time - self._last_spread_sample >= 5:
            self._spread_history.append({
                "timestamp": now.isoformat(),
                "spread_bps": f.spread_bps,
            })
            self._last_spread_sample = current_time
        self._volatility_history.append({
            "timestamp": now.isoformat(),
            "volatility_bps": f.volatility_bps,
        })

    # ── Broadcast Loop ────────────────────────────────────────────

    async def _broadcast_loop(self):
        """Periodically calculate features, run ML, and broadcast to clients."""
        tick = 0
        while self._running:
            try:
                features = self.calculate_features()
                features_dict = features.to_dict()
                await broadcast_market_update(features_dict)

                # Feed ML engine every tick
                ml_engine.ingest(features_dict)

                # ML prediction + insights every 2nd tick (1/sec)
                if tick % 2 == 0:
                    prediction = ml_engine.predict()
                    await broadcast_prediction(prediction)

                    # Lazy import to avoid circular dependency
                    from api.analytics import evaluate_rules
                    insights = evaluate_rules(features_dict)
                    if insights:
                        await broadcast_insight(insights)

                tick += 1
                await asyncio.sleep(0.5)  # 2 ticks/second
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                await asyncio.sleep(1)

    # ── Public API ────────────────────────────────────────────────

    def get_features(self) -> Features:
        return self._current_features

    def get_trades(self, limit: int = 50) -> List[dict]:
        trades = list(self._trades)[-limit:]
        return [
            {
                "price": t.price,
                "quantity": t.quantity,
                "is_buyer_maker": t.is_buyer_maker,
                "trade_id": t.trade_id,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in trades
        ]

    def get_order_book(self) -> dict:
        if not self._depth:
            return {"bids": [], "asks": [], "best_bid": 0, "best_ask": 0}
        d = self._depth[-1]
        return {
            "bids": [{"price": p, "quantity": q} for p, q in d.bids],
            "asks": [{"price": p, "quantity": q} for p, q in d.asks],
            "best_bid": d.best_bid,
            "best_ask": d.best_ask,
            "bid_volume": d.bid_volume,
            "ask_volume": d.ask_volume,
            "timestamp": d.timestamp.isoformat(),
        }

    def get_price_chart_data(self, window_seconds: int = 120) -> List[dict]:
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        return [p for p in self._price_history if p["timestamp"] >= cutoff.isoformat()]

    def get_spread_chart_data(self) -> List[dict]:
        return list(self._spread_history)

    def get_volatility_chart_data(self) -> List[dict]:
        return list(self._volatility_history)

    def get_stats(self) -> dict:
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        return {
            "connected": self._connected,
            "status": self._status,
            "trade_count": self._trade_count,
            "uptime_seconds": uptime,
            "buffer_sizes": {
                "trades": len(self._trades),
                "depth": len(self._depth),
                "price_history": len(self._price_history),
            },
            "last_update": self._last_update.isoformat() if self._last_update else None,
        }

    @property
    def is_connected(self) -> bool:
        return self._connected


# ── Singleton ─────────────────────────────────────────────────────
market_service = MarketDataService()
