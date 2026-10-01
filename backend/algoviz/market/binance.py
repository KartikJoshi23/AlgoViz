"""
Binance spot source
===================

Combined stream `<symbol>@trade` + `<symbol>@depth@100ms` over WebSocket,
REST `/api/v3/depth` snapshots for book synchronisation, and an ordered list
of hosts to fall back through when one returns HTTP 451 (geo-restriction).

`parse_stream_message()` is also used by the replay source so recordings go
through the exact same parser as live data.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

import httpx
import orjson
import websockets

from algoviz.market.events import (
    DepthDiffEvent,
    DepthSnapshotEvent,
    MarketEvent,
    SourceStatusEvent,
    TradeEvent,
)
from algoviz.market.sources import Emit, MarketSource

logger = logging.getLogger("algoviz.binance")

SNAPSHOT_LIMIT = 1000


def _levels(raw: list[list[str]]) -> list[tuple[float, float]]:
    return [(float(p), float(q)) for p, q in raw]


def parse_stream_message(raw: str | bytes, symbol: str) -> MarketEvent | None:
    """Parse one combined-stream message; None for unknown/malformed payloads."""
    try:
        msg = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return None
    data = msg.get("data", msg)
    kind = data.get("e")
    try:
        if kind == "trade":
            return TradeEvent(
                symbol=symbol,
                ts_ms=int(data["T"]),
                price=float(data["p"]),
                qty=float(data["q"]),
                is_buyer_maker=bool(data["m"]),
                trade_id=int(data["t"]),
            )
        if kind == "depthUpdate":
            return DepthDiffEvent(
                symbol=symbol,
                ts_ms=int(data["E"]),
                first_update_id=int(data["U"]),
                final_update_id=int(data["u"]),
                bids=_levels(data.get("b", [])),
                asks=_levels(data.get("a", [])),
            )
    except (KeyError, ValueError, TypeError):
        return None
    return None


def parse_snapshot(payload: dict[str, Any], symbol: str, ts_ms: int) -> DepthSnapshotEvent:
    return DepthSnapshotEvent(
        symbol=symbol,
        ts_ms=ts_ms,
        last_update_id=int(payload["lastUpdateId"]),
        bids=_levels(payload.get("bids", [])),
        asks=_levels(payload.get("asks", [])),
    )


def _is_geo_block(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    return status == 451 or "451" in str(exc)


class BinanceSource(MarketSource):
    name = "live"
    wall_clock = True

    def __init__(self, symbol: str, *, ws_hosts: list[str], rest_hosts: list[str]) -> None:
        super().__init__(symbol)
        self._ws_hosts = list(ws_hosts)
        self._rest_hosts = list(rest_hosts)
        self._ws_idx = 0
        self._rest_idx = 0
        self._emit: Emit | None = None
        self._snapshot_task: asyncio.Task[None] | None = None
        self._http = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "AlgoViz/3.0"})
        self.messages = 0
        self.snapshots = 0
        self.reconnects = 0
        self.last_message_ms = 0
        # Optional raw-message tap used by the recorder.
        self.raw_tap: Any = None

    def _stream_url(self, host: str) -> str:
        s = self.symbol.lower()
        return f"{host}/stream?streams={s}@trade/{s}@depth@100ms"

    async def run(self, emit: Emit) -> None:
        self._emit = emit
        attempt = 0
        try:
            while True:
                host = self._ws_hosts[self._ws_idx % len(self._ws_hosts)]
                self.status = "connecting"
                emit(SourceStatusEvent(self.symbol, self.now_ms(), "connecting", host))
                try:
                    async with websockets.connect(
                        self._stream_url(host),
                        ping_interval=20,
                        ping_timeout=10,
                        close_timeout=5,
                        max_size=4 * 1024 * 1024,
                    ) as ws:
                        self.status = "connected"
                        attempt = 0
                        logger.info("%s connected to %s", self.symbol, host)
                        emit(SourceStatusEvent(self.symbol, self.now_ms(), "connected", host))
                        async for raw in ws:
                            self.messages += 1
                            self.last_message_ms = self.now_ms()
                            if self.raw_tap is not None:
                                self.raw_tap(raw)
                            ev = parse_stream_message(raw, self.symbol)
                            if ev is not None:
                                emit(ev)
                except asyncio.CancelledError:
                    raise
                except websockets.exceptions.ConnectionClosed as exc:
                    logger.warning("%s stream closed: %s", self.symbol, exc)
                except Exception as exc:
                    if _is_geo_block(exc):
                        logger.warning("HTTP 451 from %s — switching host", host)
                        self.status = "geo_blocked"
                        self._ws_idx += 1
                        if self._ws_idx % len(self._ws_hosts) == 0:
                            emit(SourceStatusEvent(self.symbol, self.now_ms(), "geo_blocked", host))
                            await asyncio.sleep(120)
                        continue
                    logger.error("%s stream error: %s", self.symbol, exc)

                self.status = "reconnecting"
                self.reconnects += 1
                attempt += 1
                delay = min(2**attempt, 30)
                emit(SourceStatusEvent(self.symbol, self.now_ms(), "reconnecting", f"{delay}s"))
                await asyncio.sleep(delay)
        finally:
            self.status = "stopped"
            if self._snapshot_task:
                self._snapshot_task.cancel()
            with contextlib.suppress(Exception):
                await self._http.aclose()

    # ── Snapshot ──────────────────────────────────────────────────

    async def request_snapshot(self) -> None:
        if self._snapshot_task and not self._snapshot_task.done():
            return
        self._snapshot_task = asyncio.create_task(
            self._fetch_snapshot(), name=f"snap-{self.symbol}"
        )

    async def _fetch_snapshot(self) -> None:
        # Let a few diffs buffer first so the snapshot's lastUpdateId falls inside them.
        await asyncio.sleep(0.5)
        for _ in range(len(self._rest_hosts)):
            host = self._rest_hosts[self._rest_idx % len(self._rest_hosts)]
            url = f"{host}/api/v3/depth"
            try:
                r = await self._http.get(
                    url, params={"symbol": self.symbol, "limit": SNAPSHOT_LIMIT}
                )
                if r.status_code == 451:
                    raise httpx.HTTPStatusError("451", request=r.request, response=r)
                r.raise_for_status()
                snap = parse_snapshot(r.json(), self.symbol, int(time.time() * 1000))
                self.snapshots += 1
                if self.raw_tap is not None:
                    self.raw_tap(("snapshot", r.content))
                if self._emit:
                    self._emit(snap)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if _is_geo_block(exc):
                    logger.warning("REST 451 from %s — switching host", host)
                    self._rest_idx += 1
                    continue
                logger.error("snapshot fetch failed (%s): %s", host, exc)
                await asyncio.sleep(2)
        logger.error("%s: no REST host could serve a depth snapshot", self.symbol)

    def stats(self) -> dict[str, object]:
        return {
            **super().stats(),
            "ws_host": self._ws_hosts[self._ws_idx % len(self._ws_hosts)],
            "messages": self.messages,
            "snapshots": self.snapshots,
            "reconnects": self.reconnects,
            "last_message_ms": self.last_message_ms,
        }
