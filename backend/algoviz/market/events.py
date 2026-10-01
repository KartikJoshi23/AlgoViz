"""
Market events
=============

The normalised event vocabulary every data source emits and every consumer
understands. Timestamps are exchange event time in **milliseconds** (int);
prices/quantities are floats. Sources (live Binance, replay, synthetic) all
produce exactly these types, which is what makes replay a faithful re-run of
the live pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Level = tuple[float, float]  # (price, quantity); quantity 0 ⇒ remove level
Side = Literal["buy", "sell"]


@dataclass(slots=True)
class TradeEvent:
    symbol: str
    ts_ms: int
    price: float
    qty: float
    is_buyer_maker: bool  # True ⇒ the aggressor sold (Binance semantics)
    trade_id: int

    @property
    def side(self) -> Side:
        return "sell" if self.is_buyer_maker else "buy"

    @property
    def notional(self) -> float:
        return self.price * self.qty


@dataclass(slots=True)
class DepthDiffEvent:
    """Incremental L2 update (`<symbol>@depth@100ms`)."""

    symbol: str
    ts_ms: int
    first_update_id: int  # U
    final_update_id: int  # u
    bids: list[Level] = field(default_factory=list)
    asks: list[Level] = field(default_factory=list)


@dataclass(slots=True)
class DepthSnapshotEvent:
    """Full L2 snapshot (REST `/api/v3/depth`, or a recorded/synthetic one)."""

    symbol: str
    ts_ms: int
    last_update_id: int
    bids: list[Level] = field(default_factory=list)
    asks: list[Level] = field(default_factory=list)


@dataclass(slots=True)
class SourceStatusEvent:
    """Connection lifecycle notifications from a source."""

    symbol: str
    ts_ms: int
    status: str  # connecting | connected | reconnecting | geo_blocked | failed | finished
    detail: str = ""


MarketEvent = TradeEvent | DepthDiffEvent | DepthSnapshotEvent | SourceStatusEvent
