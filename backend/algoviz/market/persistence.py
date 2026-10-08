"""
Bar persistence
===============

Batched writer for `market_snapshots`: bars are queued at 1 Hz and flushed
every few seconds in multi-row inserts (ignoring duplicates on the
(symbol, timestamp) unique index), chunked so a backlog never exceeds the
database's bound-parameter limit. An hourly prune enforces the retention
windows for bars, predictions and alert history. Reads (`load_bars`,
`iter_bars`) serve the REST history endpoint, the WS snapshot-on-connect,
training-set reconstruction and the backtester. Exports (`write_bar_export`,
`read_bar_exports`) keep bars past retention for offline study.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import json
import logging
from collections.abc import AsyncIterator, Iterable, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algoviz.core.time import from_ms, to_ms, utcnow
from algoviz.market.bars import Bar
from algoviz.models import AlertHistory, MarketSnapshot, Prediction

logger = logging.getLogger("algoviz.persist")

FLUSH_INTERVAL_S = 5.0
PRUNE_INTERVAL_S = 3600.0
MAX_QUEUE = 3600  # an hour of bars if the DB is unavailable
# ~30 columns per bar: 500 rows ≈ 15 k bound parameters, under SQLite's 32 766 limit.
INSERT_CHUNK = 500


def bar_to_row(bar: Bar) -> dict[str, Any]:
    return {
        "symbol": bar.symbol,
        "timestamp": from_ms(bar.ts_ms),
        "source": bar.source,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "last_price": bar.last_price,
        "volume": bar.volume,
        "buy_volume": bar.buy_volume,
        "trade_count": bar.trade_count,
        "spread_bps": bar.spread_bps,
        "microprice": bar.microprice,
        "imbalance": bar.imbalance,
        "imbalance_w": bar.imbalance_w,
        "ofi": bar.ofi,
        "liquidity_5bps": bar.liquidity_5bps,
        "liquidity_10bps": bar.liquidity_10bps,
        "book_slope": bar.book_slope,
        "vwap": bar.vwap,
        "velocity": bar.velocity,
        "buy_pressure": bar.buy_pressure,
        "volatility_bps": bar.volatility_bps,
        "spread_z": bar.spread_z,
        "velocity_z": bar.velocity_z,
        "vol_z": bar.vol_z,
        "ofi_z": bar.ofi_z,
        "imbalance_z": bar.imbalance_z,
        "regime": bar.regime,
        "trend": bar.trend,
        "extra": bar.extra or None,
    }


def row_to_bar(row: MarketSnapshot) -> Bar:
    ts = row.timestamp
    return Bar(
        symbol=row.symbol,
        ts_ms=int(ts.timestamp() * 1000),
        source=row.source,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        last_price=row.last_price,
        volume=row.volume,
        buy_volume=row.buy_volume,
        trade_count=row.trade_count,
        spread_bps=row.spread_bps,
        microprice=row.microprice,
        imbalance=row.imbalance,
        imbalance_w=row.imbalance_w,
        ofi=row.ofi,
        liquidity_5bps=row.liquidity_5bps,
        liquidity_10bps=row.liquidity_10bps,
        book_slope=row.book_slope,
        vwap=row.vwap,
        velocity=row.velocity,
        buy_pressure=row.buy_pressure,
        volatility_bps=row.volatility_bps,
        spread_z=row.spread_z,
        velocity_z=row.velocity_z,
        vol_z=row.vol_z,
        ofi_z=row.ofi_z,
        imbalance_z=row.imbalance_z,
        regime=row.regime,
        trend=row.trend,
        extra=dict(row.extra or {}),
    )


class BarSink(Protocol):
    """Where an engine hands each closed bar: the database writer, or a collector."""

    def enqueue(self, bar: Bar) -> None: ...


class BarCollector:
    """A sink that keeps every closed bar in memory (synthetic history for backtests and the e2e seed)."""

    def __init__(self) -> None:
        self.bars: list[Bar] = []

    def enqueue(self, bar: Bar) -> None:
        self.bars.append(bar)


class BarWriter:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        retention_days: int,
        prediction_retention_days: int | None = None,
        alert_retention_days: int | None = None,
        enabled: bool = True,
    ) -> None:
        self._sf = session_factory
        self._retention = timedelta(days=retention_days)
        self._prediction_retention = timedelta(days=prediction_retention_days or retention_days)
        self._alert_retention = timedelta(days=alert_retention_days or retention_days)
        self._enabled = enabled
        self._queue: list[dict[str, Any]] = []
        self._task: asyncio.Task[None] | None = None
        self.written = 0
        self.failed_flushes = 0
        self._last_prune = 0.0

    @property
    def queued(self) -> int:
        return len(self._queue)

    def enqueue(self, bar: Bar) -> None:
        if not self._enabled:
            return
        if len(self._queue) >= MAX_QUEUE:
            del self._queue[: len(self._queue) - MAX_QUEUE + 1]
        self._queue.append(bar_to_row(bar))

    async def start(self) -> None:
        if self._enabled and self._task is None:
            self._task = asyncio.create_task(self._loop(), name="bar-writer")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush()

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            await self.flush()
            now = loop.time()
            if now - self._last_prune >= PRUNE_INTERVAL_S:
                self._last_prune = now
                await self.prune()

    async def flush(self) -> None:
        if not self._queue:
            return
        rows, self._queue = self._queue, []
        try:
            async with self._sf() as session:
                bind = session.get_bind()
                insert = pg_insert if bind.dialect.name == "postgresql" else sqlite_insert
                for i in range(0, len(rows), INSERT_CHUNK):
                    stmt = insert(MarketSnapshot).values(rows[i : i + INSERT_CHUNK])
                    stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timestamp"])
                    await session.execute(stmt)
                await session.commit()
            self.written += len(rows)
        except Exception:
            self.failed_flushes += 1
            logger.exception("bar flush failed (%d rows re-queued)", len(rows))
            self._queue = rows + self._queue
            if len(self._queue) > MAX_QUEUE:
                del self._queue[: len(self._queue) - MAX_QUEUE]

    async def prune(self) -> dict[str, int]:
        """Enforce the retention windows; returns rows deleted per table."""
        now = utcnow()
        targets = (
            (
                "bars",
                delete(MarketSnapshot).where(MarketSnapshot.timestamp < now - self._retention),
            ),
            (
                "predictions",
                delete(Prediction).where(Prediction.timestamp < now - self._prediction_retention),
            ),
            (
                "alert_history",
                delete(AlertHistory).where(AlertHistory.triggered_at < now - self._alert_retention),
            ),
        )
        deleted: dict[str, int] = {}
        try:
            async with self._sf() as session:
                for name, stmt in targets:
                    result = await session.execute(stmt)
                    deleted[name] = int(result.rowcount or 0)  # type: ignore[attr-defined]
                await session.commit()
                if session.get_bind().dialect.name == "sqlite":
                    await session.execute(text("PRAGMA optimize"))
        except Exception:
            logger.exception("retention prune failed")
            return deleted
        if any(deleted.values()):
            logger.info("retention prune: %s", deleted)
        return deleted


async def load_bars(
    session_factory: async_sessionmaker[AsyncSession],
    symbol: str,
    *,
    source: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 3600,
    newest_first: bool = False,
) -> list[Bar]:
    """
    Persisted bars for `symbol`, oldest first unless `newest_first`. Pass the
    running data source so a simulator's bars are never mixed into history
    that trains the live model or feeds a backtest labelled "history".
    """
    q = select(MarketSnapshot).where(MarketSnapshot.symbol == symbol)
    if source is not None:
        q = q.where(MarketSnapshot.source == source)
    if start_ms is not None:
        q = q.where(MarketSnapshot.timestamp >= from_ms(start_ms))
    if end_ms is not None:
        q = q.where(MarketSnapshot.timestamp < from_ms(end_ms))
    order = MarketSnapshot.timestamp.desc() if newest_first else MarketSnapshot.timestamp.asc()
    q = q.order_by(order).limit(limit)
    async with session_factory() as session:
        rows = (await session.execute(q)).scalars().all()
    return [row_to_bar(r) for r in rows]


async def iter_bars(
    session_factory: async_sessionmaker[AsyncSession],
    symbol: str,
    *,
    source: str | None,
    start_ms: int,
    limit: int,
    chunk: int = 10_000,
) -> AsyncIterator[list[Bar]]:
    """
    Persisted bars from `start_ms` onwards, oldest first, in chunks of at most
    `chunk` (keyset pagination on the timestamp): a long backtest never holds
    a full result set of ORM rows in memory at once.
    """
    after_ms, remaining = start_ms, limit
    while remaining > 0:
        page = await load_bars(
            session_factory, symbol, source=source, start_ms=after_ms, limit=min(chunk, remaining)
        )
        if not page:
            return
        yield page
        remaining -= len(page)
        after_ms = page[-1].ts_ms + 1


async def bar_coverage(
    session_factory: async_sessionmaker[AsyncSession], symbol: str, source: str, since_ms: int
) -> tuple[int, int, int | None, int | None]:
    """
    Persisted bars of `symbol` from `source`: how many, how many from `since_ms`
    on, and the oldest and newest open time (ms).
    """
    since = from_ms(since_ms)
    q = select(
        func.count(),
        func.count().filter(MarketSnapshot.timestamp >= since),
        func.min(MarketSnapshot.timestamp),
        func.max(MarketSnapshot.timestamp),
    ).where(MarketSnapshot.symbol == symbol, MarketSnapshot.source == source)
    async with session_factory() as session:
        n, n_since, oldest, newest = (await session.execute(q)).one()
    return (
        int(n),
        int(n_since),
        None if oldest is None else to_ms(oldest),
        None if newest is None else to_ms(newest),
    )


async def newest_bar_ms(
    session_factory: async_sessionmaker[AsyncSession], symbol: str, source: str
) -> int | None:
    """The newest persisted bar's open time (ms): a walk down the (symbol, timestamp) index."""
    q = select(func.max(MarketSnapshot.timestamp)).where(
        MarketSnapshot.symbol == symbol, MarketSnapshot.source == source
    )
    async with session_factory() as session:
        newest = (await session.execute(q)).scalar_one()
    return None if newest is None else to_ms(newest)


# ── Exports (bars past retention) ─────────────────────────────────


def write_bar_export(bars: Sequence[Bar], path: Path) -> None:
    """Bars as gzipped NDJSON, one `Bar.to_dict()` per line, in the order given."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as fh:
        for bar in bars:
            fh.write(json.dumps(bar.to_dict(), separators=(",", ":")) + "\n")


def read_bar_exports(paths: Iterable[Path]) -> list[Bar]:
    """Bars from export files, oldest first, one per (symbol, source, open time)."""
    bars: dict[tuple[str, str, int], Bar] = {}
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    bar = Bar(**json.loads(line))
                    bars[(bar.symbol, bar.source, bar.ts_ms)] = bar
    return sorted(bars.values(), key=lambda b: b.ts_ms)
