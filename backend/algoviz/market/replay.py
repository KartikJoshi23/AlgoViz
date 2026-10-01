"""
Replay source
=============

Plays back an NDJSON recording (optionally gzip-compressed) of raw Binance
messages through the same parser as the live source. Line format:

    {"ts": <receive-time ms>, "kind": "ws",       "data": <raw combined-stream message>}
    {"ts": <receive-time ms>, "kind": "snapshot", "data": {"lastUpdateId":…, "bids":…, "asks":…}}

A recording contains a REST snapshot near its start (a few diffs precede it,
exactly as the live sync procedure buffers them) so the book syncs immediately.
Pacing follows the recorded inter-arrival times divided by `speed`;
`speed=0` means "as fast as possible" (tests). When looping, timestamps are
shifted forward so time stays monotonic; the book re-syncs from the
recording's own snapshot on each loop.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
from pathlib import Path
from typing import IO, Any, cast

import orjson

from algoviz.market.binance import parse_snapshot, parse_stream_message
from algoviz.market.events import DepthDiffEvent, SourceStatusEvent, TradeEvent
from algoviz.market.sources import Emit, MarketSource

logger = logging.getLogger("algoviz.replay")

_MAX_SLEEP_S = 2.0


def open_recording(path: Path) -> IO[bytes]:
    if str(path).endswith(".gz"):
        return cast(IO[bytes], gzip.open(path, "rb"))
    return open(path, "rb")


class ReplaySource(MarketSource):
    name = "replay"
    # now_ms() is the *recorded receive clock*, which sits ahead of exchange event
    # time by the same network/clock skew the live source sees → same correction.
    wall_clock = True

    def __init__(self, symbol: str, path: Path, *, speed: float = 1.0, loop: bool = True) -> None:
        super().__init__(symbol)
        self.path = Path(path)
        self.speed = speed
        self.loop = loop
        self.time_scale = speed  # 0 = unpaced (as fast as possible)
        self._offset_ms = 0
        # Trade ids are shifted by one recording's id span per loop, so consumers
        # that de-duplicate on a monotonic id keep accepting the replayed tape.
        self._id_offset = 0
        self._pass_ids: tuple[int, int] | None = None  # (min, max) original ids seen this pass
        self._now_ms = 0
        self.records = 0
        self.loops = 0
        self.finished = asyncio.Event()

    def now_ms(self) -> int:
        return self._now_ms

    async def request_snapshot(self) -> None:
        # Snapshots are part of the recording; nothing to fetch.
        return None

    async def run(self, emit: Emit) -> None:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.status = "connected"
        try:
            while True:
                first_ts, last_ts = await self._play_once(emit)
                self.loops += 1
                if not self.loop or first_ts is None or last_ts is None:
                    break
                self._offset_ms += (last_ts - first_ts) + 1000
                if self._pass_ids is not None:
                    self._id_offset += self._pass_ids[1] - self._pass_ids[0] + 1
                    self._pass_ids = None
            self.status = "finished"
            emit(SourceStatusEvent(self.symbol, self._now_ms, "finished", str(self.path.name)))
        finally:
            self.finished.set()

    async def _play_once(self, emit: Emit) -> tuple[int | None, int | None]:
        first_ts: int | None = None
        prev_ts: int | None = None
        last_ts: int | None = None
        debt_s = 0.0
        with open_recording(self.path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec: dict[str, Any] = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue
                ts = int(rec["ts"])
                if first_ts is None:
                    first_ts = ts
                if prev_ts is not None and self.speed > 0:
                    debt_s += max(ts - prev_ts, 0) / 1000.0 / self.speed
                    if debt_s >= 0.002:
                        await asyncio.sleep(min(debt_s, _MAX_SLEEP_S))
                        debt_s = 0.0
                elif self.speed <= 0 and self.records % 100 == 0:
                    await self.yield_to_consumer()  # let the loop (and the pipeline) catch up
                prev_ts = last_ts = ts
                self._now_ms = ts + self._offset_ms
                self.records += 1

                kind = rec.get("kind")
                if kind == "snapshot":
                    ev = parse_snapshot(rec["data"], self.symbol, self._now_ms)
                    emit(ev)
                elif kind == "ws":
                    data = rec["data"]
                    raw = data if isinstance(data, str | bytes) else orjson.dumps(data)
                    pev = parse_stream_message(raw, self.symbol)
                    if pev is None:
                        continue
                    if isinstance(pev, TradeEvent | DepthDiffEvent):
                        pev.ts_ms += self._offset_ms
                    if isinstance(pev, TradeEvent):
                        lo, hi = self._pass_ids or (pev.trade_id, pev.trade_id)
                        self._pass_ids = (min(lo, pev.trade_id), max(hi, pev.trade_id))
                        pev.trade_id += self._id_offset
                    emit(pev)
        return first_ts, last_ts

    def stats(self) -> dict[str, object]:
        return {
            **super().stats(),
            "file": self.path.name,
            "speed": self.speed,
            "records": self.records,
            "loops": self.loops,
        }
