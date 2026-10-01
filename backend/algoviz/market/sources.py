"""
Data source interface
=====================

A source pushes normalised `MarketEvent`s into the engine and owns its own
clock (`now_ms`) so replay can run faster than real time while bars, windows
and baselines still see consistent timestamps.

An *unpaced* source (`time_scale == 0`: replay or synthetic "as fast as
possible") runs as fast as the **pipeline** can go, not faster: at its yield
points it awaits `yield_to_consumer()`, which the engine wires to the
intelligence tier's backlog, so every bar is predicted and none is dropped.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from algoviz.config import Settings
from algoviz.market.events import MarketEvent

Emit = Callable[[MarketEvent], None]


class MarketSource(ABC):
    name: str = "abstract"
    # True when now_ms() is the local wall clock and event timestamps come from an
    # exchange whose clock may differ (the engine then estimates and removes the skew).
    wall_clock: bool = False

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.upper()
        self.status = "idle"
        self.time_scale = 1.0
        # Set by the engine for unpaced runs: resolves once downstream has room.
        self.backpressure: Callable[[], Awaitable[None]] | None = None

    @property
    def unpaced(self) -> bool:
        return self.time_scale <= 0

    async def yield_to_consumer(self) -> None:
        """An unpaced source's yield point: wait for the pipeline, or at least let it run."""
        if self.backpressure is not None:
            await self.backpressure()
        else:
            await asyncio.sleep(0)

    @property
    def connected(self) -> bool:
        return self.status == "connected"

    def now_ms(self) -> int:
        return int(time.time() * 1000)

    @abstractmethod
    async def run(self, emit: Emit) -> None:
        """Run until cancelled (or until the data is exhausted for non-looping replay)."""

    @abstractmethod
    async def request_snapshot(self) -> None:
        """Arrange for a `DepthSnapshotEvent` to be emitted as soon as possible."""

    def stats(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status, "time_scale": self.time_scale}


def create_source(cfg: Settings, symbol: str) -> MarketSource:
    if cfg.DATA_SOURCE == "live":
        from algoviz.market.binance import BinanceSource

        return BinanceSource(
            symbol, ws_hosts=cfg.BINANCE_WS_HOSTS, rest_hosts=cfg.BINANCE_REST_HOSTS
        )
    if cfg.DATA_SOURCE == "replay":
        from algoviz.market.replay import ReplaySource

        assert cfg.REPLAY_FILE is not None
        return ReplaySource(symbol, cfg.REPLAY_FILE, speed=cfg.REPLAY_SPEED, loop=True)
    from algoviz.market.synthetic import SyntheticSource

    return SyntheticSource(symbol)
