"""WebSocket hub — subscriptions, latest-wins vs reliable delivery, shedding, protocol."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import orjson

from algoviz.ws.hub import RELIABLE_QUEUE_MAX, Hub


class FakeWS:
    """Minimal stand-in for a Starlette WebSocket with controllable send latency."""

    def __init__(self, delay: float = 0.0) -> None:
        self.sent: list[dict[str, Any]] = []
        self.delay = delay
        self.closed = False
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_bytes(self, payload: bytes) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent.append(orjson.loads(payload))

    async def close(self) -> None:
        self.closed = True

    def types(self) -> list[str]:
        return [m["type"] for m in self.sent]


def _hub() -> Hub:
    hub = Hub()

    async def snapshot(symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "bars": {"columns": [], "rows": []}}

    hub.configure(
        symbols=["BTCUSDT", "ETHUSDT"],
        snapshot_provider=snapshot,
        hello_provider=lambda subscribed: {"subscribed": subscribed},
    )
    return hub


async def _settle() -> None:
    await asyncio.sleep(0.02)


async def test_connect_sends_hello_then_snapshot_with_default_channels() -> None:
    hub = _hub()
    ws = FakeWS()
    client = await hub.connect(ws)  # type: ignore[arg-type]
    await _settle()
    assert ws.accepted and ws.types()[:2] == ["hello", "snapshot"]
    assert "book" not in client.channels and "features" in client.channels
    assert ws.sent[1]["symbol"] == "BTCUSDT"
    await hub.disconnect(ws)  # type: ignore[arg-type]
    assert ws.closed and hub.active_count == 0


async def test_publish_respects_channel_and_symbol_filters() -> None:
    hub = _hub()
    btc, eth = FakeWS(), FakeWS()
    await hub.connect(btc)  # type: ignore[arg-type]
    await hub.connect(eth, symbol="ETHUSDT")  # type: ignore[arg-type]
    await _settle()
    hub.publish("features", "BTCUSDT", {"x": 1})
    hub.publish("book", "BTCUSDT", {"x": 2})  # nobody subscribed to book
    hub.publish("bars", "ETHUSDT", {"columns": [], "rows": [[1]]})
    await _settle()
    assert btc.types()[2:] == ["features"]
    assert eth.types()[2:] == ["bar"]  # 'bars' channel is delivered as type 'bar'
    assert not hub.has_subscribers("book") and hub.has_subscribers("features", "ETHUSDT")
    await hub.close_all()


async def test_latest_wins_collapses_backlog_for_slow_client() -> None:
    hub = _hub()
    ws = FakeWS(delay=0.02)
    client = await hub.connect(ws)  # type: ignore[arg-type]
    await asyncio.sleep(0.1)  # hello + snapshot delivered
    for i in range(50):
        hub.publish("features", "BTCUSDT", {"i": i})
    await asyncio.sleep(0.15)
    feats = [m for m in ws.sent if m["type"] == "features"]
    assert 1 <= len(feats) <= 3 and feats[-1]["data"]["i"] == 49
    assert client.dropped >= 40
    await hub.close_all()


async def test_reliable_queue_sheds_trades_first_then_closes() -> None:
    hub = _hub()
    ws = FakeWS(delay=10.0)  # effectively stuck
    client = await hub.connect(ws)  # type: ignore[arg-type]
    await _settle()
    for i in range(RELIABLE_QUEUE_MAX + 20):
        hub.publish("trades", "BTCUSDT", [{"i": i}])
    assert client.dropped >= 20 and len(client.fifo) <= RELIABLE_QUEUE_MAX
    # alerts are never shed; overflowing with undroppable frames marks the client for closing
    for i in range(RELIABLE_QUEUE_MAX + 5):
        hub.publish("alerts", "BTCUSDT", {"i": i})
    assert any(ch == "__overflow__" for ch, _ in client.fifo)
    await hub.close_all()


async def test_subscribe_switch_symbol_and_ping() -> None:
    hub = _hub()
    ws = FakeWS()
    client = await hub.connect(ws)  # type: ignore[arg-type]
    await _settle()
    await hub.handle_client_message(
        ws, json.dumps({"op": "subscribe", "channels": ["book"], "symbol": "ETHUSDT"})
    )  # type: ignore[arg-type]
    await hub.handle_client_message(ws, json.dumps({"op": "ping", "ts": 7}))  # type: ignore[arg-type]
    await hub.handle_client_message(ws, json.dumps({"op": "subscribe", "symbol": "DOGE"}))  # type: ignore[arg-type]
    await hub.handle_client_message(ws, "{bad json")  # type: ignore[arg-type]
    await hub.handle_client_message(ws, json.dumps({"op": "unsubscribe", "channels": ["book"]}))  # type: ignore[arg-type]
    await _settle()
    t = ws.types()
    assert t[:2] == ["hello", "snapshot"]
    assert (
        "subscribed" in t and "pong" in t and t.count("snapshot") == 2
    )  # symbol switch re-snapshots
    assert t.count("error") == 2
    assert client.symbol == "ETHUSDT" and client.channels == set()
    pong = next(m for m in ws.sent if m["type"] == "pong")
    assert pong["data"] == {"client_ts": 7}
    await hub.close_all()


async def test_no_data_frames_before_snapshot_is_queued() -> None:
    """Frames published while the snapshot provider is still running must not precede it."""
    hub = Hub()
    gate = asyncio.Event()

    async def slow_snapshot(symbol: str) -> dict[str, Any]:
        await gate.wait()
        return {"symbol": symbol}

    hub.configure(symbols=["BTCUSDT"], snapshot_provider=slow_snapshot, hello_provider=lambda s: {})
    ws = FakeWS()
    connect = asyncio.create_task(hub.connect(ws))  # type: ignore[arg-type]
    await asyncio.sleep(0.02)  # hello sent; provider is blocked on the gate
    hub.publish("features", "BTCUSDT", {"early": True})
    hub.publish("bars", "BTCUSDT", {"columns": [], "rows": [[1]]})
    await asyncio.sleep(0.02)
    assert ws.types() == ["hello"], ws.types()
    gate.set()
    await connect
    await _settle()
    hub.publish("features", "BTCUSDT", {"early": False})
    await _settle()
    assert ws.types() == ["hello", "snapshot", "features"]
    assert ws.sent[-1]["data"] == {"early": False}
    await hub.close_all()
