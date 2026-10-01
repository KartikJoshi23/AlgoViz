"""
WebSocket hub
=============

Per-client delivery with backpressure:

- **latest-wins** channels (`features`, `book`): one slot per channel; a new
  message replaces an unsent one, so a slow client always gets the freshest
  state and never a backlog;
- **reliable** channels (everything else): bounded FIFO; if a client falls
  more than `RELIABLE_QUEUE_MAX` frames behind, the oldest *trades* batches
  are dropped first, then the client is disconnected (alerts/snapshots are
  never silently dropped).

`publish()` is synchronous so the market engine can call it from event
handlers; a sender task per client drains the queues. On connect the hub
sends `hello` and then a `snapshot` built by the registered provider, and
does the same on every symbol switch.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import orjson
from fastapi import WebSocket
from pydantic import TypeAdapter, ValidationError

from algoviz.core.time import utcnow
from algoviz.schemas.ws import (
    CHANNELS,
    DEFAULT_CHANNELS,
    LATEST_WINS_CHANNELS,
    ClientMessage,
    PingMessage,
    SubscribeMessage,
    UnsubscribeMessage,
)

logger = logging.getLogger("algoviz.ws")

SEND_TIMEOUT_S = 3.0
RELIABLE_QUEUE_MAX = 400
DISCONNECT_GRACE_S = 1.0

# Subscription channel → frame `type` (plural channels carry singular frames).
CHANNEL_TYPES: dict[str, str] = {
    "bars": "bar",
    "alerts": "alert",
    "backtests": "backtest_progress",
}

SnapshotProvider = Callable[[str], Awaitable[dict[str, Any] | None]]
HelloProvider = Callable[[list[str]], dict[str, Any]]

_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def encode(message: dict[str, Any]) -> bytes:
    return orjson.dumps(message, default=str, option=orjson.OPT_NAIVE_UTC | orjson.OPT_UTC_Z)


def now_ms() -> int:
    return int(utcnow().timestamp() * 1000)


def envelope(msg_type: str, data: Any, symbol: str | None = None) -> dict[str, Any]:
    return {"type": msg_type, "ts": now_ms(), "symbol": symbol, "data": data}


@dataclass(slots=True)
class Client:
    ws: WebSocket
    symbol: str
    channels: set[str]
    latest: dict[str, bytes] = field(default_factory=dict)
    fifo: deque[tuple[str, bytes]] = field(default_factory=deque)
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    sent: int = 0
    dropped: int = 0
    connected_at_ms: int = field(default_factory=now_ms)
    ready: bool = False  # data frames are held until the snapshot has been queued

    def enqueue(self, channel: str, payload: bytes) -> None:
        if channel in LATEST_WINS_CHANNELS:
            if channel in self.latest:
                self.dropped += 1
            self.latest[channel] = payload
        else:
            self.fifo.append((channel, payload))
            if len(self.fifo) > RELIABLE_QUEUE_MAX:
                self._shed()
        self.wake.set()

    def _shed(self) -> None:
        # Drop oldest trades batches first; they are the bulk of reliable traffic.
        for i, (ch, _) in enumerate(self.fifo):
            if ch == "trades":
                del self.fifo[i]
                self.dropped += 1
                return
        # Nothing droppable → the client is hopelessly behind; the sender will close it.
        self.fifo.append(("__overflow__", b""))


class Hub:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, Client] = {}
        self._snapshot_provider: SnapshotProvider | None = None
        self._hello_provider: HelloProvider | None = None
        self.symbols: list[str] = []
        self.default_symbol = "BTCUSDT"
        self.total_sent = 0

    # ── Wiring ────────────────────────────────────────────────────

    def configure(
        self,
        *,
        symbols: list[str],
        snapshot_provider: SnapshotProvider,
        hello_provider: HelloProvider,
    ) -> None:
        self.symbols = [s.upper() for s in symbols]
        self.default_symbol = self.symbols[0] if self.symbols else "BTCUSDT"
        self._snapshot_provider = snapshot_provider
        self._hello_provider = hello_provider

    # ── Lifecycle ─────────────────────────────────────────────────

    async def connect(self, ws: WebSocket, symbol: str | None = None) -> Client:
        await ws.accept()
        sym = (symbol or self.default_symbol).upper()
        if sym not in self.symbols and self.symbols:
            sym = self.default_symbol
        client = Client(ws=ws, symbol=sym, channels=set(DEFAULT_CHANNELS))
        self._clients[ws] = client
        client.task = asyncio.create_task(self._sender(client), name="ws-sender")
        logger.info("ws connected (%s, active=%d)", sym, len(self._clients))
        await self._send_hello(client)
        await self._send_snapshot(client)
        return client

    async def disconnect(self, ws: WebSocket) -> None:
        client = self._clients.pop(ws, None)
        if client is None:
            return
        if client.task and not client.task.done():
            client.task.cancel()
            # A task can absorb one cancellation (e.g. inside a library helper);
            # wait briefly and cancel again rather than hang forever.
            _, pending = await asyncio.wait({client.task}, timeout=DISCONNECT_GRACE_S)
            if pending:
                client.task.cancel()
                with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await asyncio.wait({client.task}, timeout=DISCONNECT_GRACE_S)
        with contextlib.suppress(Exception):
            await ws.close()
        logger.info(
            "ws disconnected (active=%d, sent=%d, dropped=%d)",
            len(self._clients),
            client.sent,
            client.dropped,
        )

    async def close_all(self) -> None:
        for ws in list(self._clients):
            await self.disconnect(ws)

    # ── Publish (sync; safe from event handlers) ──────────────────

    def publish(self, channel: str, symbol: str | None, data: Any) -> None:
        if not self._clients:
            return
        payload: bytes | None = None
        for client in self._clients.values():
            if not client.ready or channel not in client.channels:
                continue
            if symbol is not None and client.symbol != symbol:
                continue
            if payload is None:
                payload = encode(envelope(CHANNEL_TYPES.get(channel, channel), data, symbol))
            client.enqueue(channel, payload)

    def has_subscribers(self, channel: str, symbol: str | None = None) -> bool:
        return any(
            channel in c.channels and (symbol is None or c.symbol == symbol)
            for c in self._clients.values()
        )

    # ── Inbound ───────────────────────────────────────────────────

    async def handle_client_message(self, ws: WebSocket, text: str) -> None:
        client = self._clients.get(ws)
        if client is None:
            return
        try:
            msg = _client_adapter.validate_json(text)
        except ValidationError as exc:
            await self._send_now(client, envelope("error", {"message": exc.errors()[0]["msg"]}))
            return
        if isinstance(msg, PingMessage):
            await self._send_now(client, envelope("pong", {"client_ts": msg.ts}))
        elif isinstance(msg, SubscribeMessage):
            switched = False
            if msg.symbol:
                sym = msg.symbol.upper()
                if sym not in self.symbols:
                    await self._send_now(
                        client, envelope("error", {"message": f"unknown symbol {sym}"})
                    )
                    return
                switched = sym != client.symbol
                client.symbol = sym
            if msg.channels is not None:
                client.channels = {c for c in msg.channels if c in CHANNELS}
            await self._send_now(
                client,
                envelope(
                    "subscribed", {"channels": sorted(client.channels), "symbol": client.symbol}
                ),
            )
            if switched:
                client.ready = False
                client.latest.clear()
                client.fifo = deque(f for f in client.fifo if f[0] == "__control__")
                await self._send_snapshot(client)
        elif isinstance(msg, UnsubscribeMessage):
            client.channels -= set(msg.channels)
            for ch in msg.channels:
                client.latest.pop(ch, None)
            await self._send_now(
                client,
                envelope(
                    "subscribed", {"channels": sorted(client.channels), "symbol": client.symbol}
                ),
            )

    # ── Internals ─────────────────────────────────────────────────

    async def _send_hello(self, client: Client) -> None:
        data = self._hello_provider(sorted(client.channels)) if self._hello_provider else {}
        await self._send_now(client, envelope("hello", data, client.symbol))

    async def _send_snapshot(self, client: Client) -> None:
        if self._snapshot_provider is None:
            client.ready = True
            return
        try:
            snap = await self._snapshot_provider(client.symbol)
        except Exception:
            logger.exception("snapshot provider failed")
            client.ready = True
            return
        if snap is not None:
            client.enqueue("snapshot", encode(envelope("snapshot", snap, client.symbol)))
        client.ready = True

    async def _send_now(self, client: Client, message: dict[str, Any]) -> None:
        client.enqueue("__control__", encode(message))

    async def _sender(self, client: Client) -> None:
        ws = client.ws
        try:
            while True:
                await client.wake.wait()
                client.wake.clear()
                while client.fifo:
                    channel, payload = client.fifo.popleft()
                    if channel == "__overflow__":
                        logger.warning("ws client too slow; closing")
                        return
                    # asyncio.timeout(), not wait_for(): on Python 3.11 wait_for swallows a
                    # cancellation that races with the inner awaitable completing (gh-86296),
                    # which left sender tasks alive forever after disconnect.
                    async with asyncio.timeout(SEND_TIMEOUT_S):
                        await ws.send_bytes(payload)
                    client.sent += 1
                    self.total_sent += 1
                while client.latest:
                    channel, payload = client.latest.popitem()
                    async with asyncio.timeout(SEND_TIMEOUT_S):
                        await ws.send_bytes(payload)
                    client.sent += 1
                    self.total_sent += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("ws sender ended: %s", exc)
        finally:
            self._clients.pop(ws, None)
            with contextlib.suppress(Exception):
                await ws.close()

    # ── Stats ─────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        return len(self._clients)

    def stats(self) -> dict[str, Any]:
        return {
            "clients": len(self._clients),
            "total_sent": self.total_sent,
            "per_client": [
                {
                    "symbol": c.symbol,
                    "channels": sorted(c.channels),
                    "sent": c.sent,
                    "dropped": c.dropped,
                    "backlog": len(c.fifo) + len(c.latest),
                    "connected_at_ms": c.connected_at_ms,
                }
                for c in self._clients.values()
            ],
        }


ws_manager = Hub()
