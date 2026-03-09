"""
AlgoViz Backend — WebSocket Hub
=================================

Manages WebSocket connections from frontend clients and broadcasts
real-time market data, alerts, and predictions.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and message broadcasting."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(f"WebSocket connected. Active: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Active: {len(self._connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Send a message to all connected clients."""
        if not self._connections:
            return

        payload = json.dumps(message, default=str)
        dead: Set[WebSocket] = set()

        async with self._lock:
            connections = set(self._connections)

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        if dead:
            async with self._lock:
                self._connections -= dead

    async def send_to(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send a message to a specific client."""
        try:
            await websocket.send_json(message, mode="text")
        except Exception:
            await self.disconnect(websocket)

    @property
    def active_count(self) -> int:
        return len(self._connections)


# Global connection manager singleton
ws_manager = ConnectionManager()


async def broadcast_market_update(features: Dict[str, Any]):
    """Broadcast market feature update to all clients."""
    await ws_manager.broadcast({
        "type": "features",
        "data": features,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_trade(trade: Dict[str, Any]):
    """Broadcast a new trade to all clients."""
    await ws_manager.broadcast({
        "type": "trade",
        "data": trade,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_alert(alert: Dict[str, Any]):
    """Broadcast a triggered alert to all clients."""
    await ws_manager.broadcast({
        "type": "alert",
        "data": alert,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_prediction(prediction: Dict[str, Any]):
    """Broadcast an ML prediction to all clients."""
    await ws_manager.broadcast({
        "type": "prediction",
        "data": prediction,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_insight(insights: list):
    """Broadcast trading insights to all clients."""
    await ws_manager.broadcast({
        "type": "insights",
        "data": insights,
        "timestamp": datetime.utcnow().isoformat(),
    })
