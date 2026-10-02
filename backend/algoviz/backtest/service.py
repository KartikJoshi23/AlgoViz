"""
Backtest runner
===============

Turns a `POST /strategies/{id}/backtest` into a background job:

1. wait for a slot (at most `BACKTEST_MAX_CONCURRENT` run at once; the API
   refuses new jobs beyond `BACKTEST_MAX_QUEUED`);
2. load bars from `market_snapshots` for the lookback window in pages; if
   fewer than `BACKTEST_MIN_BARS` exist, generate synthetic history by running
   the synthetic source through the real engine in a worker thread (the result
   is labelled `data_source="synthetic"` so nobody mistakes it for reality);
3. join persisted predictions by timestamp when the strategy uses `p_up`/`p_down`;
4. run the engine in a thread, streaming `backtest_progress` frames;
5. persist metrics, trades and the equity curve on the `BacktestResult` row.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algoviz.backtest.engine import BacktestOutcome, run_backtest
from algoviz.backtest.strategy import StrategySpec
from algoviz.config import Settings
from algoviz.core.time import from_ms, utcnow
from algoviz.core.workers import run_in_thread
from algoviz.market.bars import Bar
from algoviz.market.persistence import BarCollector, iter_bars
from algoviz.models import BacktestResult, Prediction
from algoviz.ws.hub import Hub

logger = logging.getLogger("algoviz.backtest")


class BacktestBusy(RuntimeError):
    """Too many backtests running or waiting; the API maps this to HTTP 429."""


def generate_synthetic_bars(symbol: str, n_bars: int, seed: int = 42) -> list[Bar]:
    """Run the synthetic source through the real engine (own event loop, worker thread)."""
    from algoviz.config import settings as global_settings
    from algoviz.market.service import SymbolEngine
    from algoviz.market.synthetic import SyntheticSource

    async def _run() -> list[Bar]:
        src = SyntheticSource(symbol, seed=seed, speed=0, start_ms=1_700_000_000_000)
        # Every closed bar, not the engine's chart ring (which keeps only the last 600).
        sink = BarCollector()
        # This already runs in its own thread and loop: HMM fits stay in-process here.
        engine = SymbolEngine(
            symbol,
            global_settings,
            src,
            Hub(),
            writer=sink,
            preload=False,
            intelligence=False,
            offload=run_in_thread,
        )
        await engine.start()
        try:
            while len(sink.bars) < n_bars:  # noqa: ASYNC110 — polling a counter
                await asyncio.sleep(0.02)
        finally:
            await engine.stop()
        return sink.bars[:n_bars]

    return asyncio.run(_run())


class BacktestRunner:
    def __init__(self, cfg: Settings, sf: async_sessionmaker[AsyncSession], hub: Hub) -> None:
        self.cfg = cfg
        self._sf = sf
        self._hub = hub
        self._jobs: dict[int, asyncio.Task[None]] = {}
        self._synthetic_cache: dict[str, list[Bar]] = {}
        self._slots = asyncio.Semaphore(cfg.BACKTEST_MAX_CONCURRENT)
        self.max_queued = cfg.BACKTEST_MAX_QUEUED

    # ── Data ──────────────────────────────────────────────────────

    async def _history(
        self, symbol: str, lookback_minutes: int, now_ms: int
    ) -> tuple[list[Bar], str]:
        bars: list[Bar] = []
        async for page in iter_bars(
            self._sf,
            symbol,
            source=self.cfg.DATA_SOURCE,
            start_ms=now_ms - lookback_minutes * 60_000,
            limit=min(lookback_minutes * 60, self.cfg.BACKTEST_MAX_BARS),
        ):
            bars.extend(page)
        if len(bars) >= self.cfg.BACKTEST_MIN_BARS:
            return bars, "history"
        if symbol not in self._synthetic_cache:
            logger.info(
                "%s: only %d bars of history; generating synthetic history", symbol, len(bars)
            )
            self._synthetic_cache[symbol] = await asyncio.to_thread(
                generate_synthetic_bars, symbol, self.cfg.BACKTEST_SYNTHETIC_BARS
            )
        return list(self._synthetic_cache[symbol]), "synthetic"

    async def _predictions(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> dict[int, dict[str, float]]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(Prediction.timestamp, Prediction.p_up, Prediction.p_down)
                    .where(
                        Prediction.symbol == symbol,
                        Prediction.timestamp >= from_ms(start_ms),
                        Prediction.timestamp <= from_ms(end_ms),
                    )
                    .order_by(Prediction.timestamp)
                )
            ).all()
        out: dict[int, dict[str, float]] = {}
        for ts, p_up, p_down in rows:
            out[int(ts.timestamp() * 1000)] = {"p_up": float(p_up), "p_down": float(p_down)}
        return out

    # ── Jobs ──────────────────────────────────────────────────────

    def has_capacity(self) -> bool:
        return len(self._jobs) < self.max_queued

    def submit(self, result_id: int, symbol: str, spec: StrategySpec, req: dict[str, Any]) -> None:
        if not self.has_capacity():
            raise BacktestBusy(f"{len(self._jobs)} backtests already running or queued")
        task = asyncio.create_task(
            self._run_job(result_id, symbol, spec, req), name=f"backtest-{result_id}"
        )
        self._jobs[result_id] = task
        task.add_done_callback(lambda _t: self._jobs.pop(result_id, None))

    def running(self) -> list[int]:
        return sorted(self._jobs)

    async def stop(self) -> None:
        """Cancel every job; each marks its row failed before the database closes."""
        jobs = list(self._jobs.values())
        for task in jobs:
            task.cancel()
        for task in jobs:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _run_job(
        self, result_id: int, symbol: str, spec: StrategySpec, req: dict[str, Any]
    ) -> None:
        loop = asyncio.get_running_loop()

        def publish(
            status: str, done: int, total: int, extra: dict[str, Any] | None = None
        ) -> None:
            self._hub.publish(
                "backtests",
                symbol,
                {
                    "backtest_id": result_id,
                    "status": status,
                    "done": done,
                    "total": total,
                    **(extra or {}),
                },
            )

        try:
            if self._slots.locked():
                publish("queued", 0, 0)
            async with self._slots:
                await self._set_status(result_id, "running")
                now_ms = int(utcnow().timestamp() * 1000)
                bars, source = await self._history(symbol, int(req["lookback_minutes"]), now_ms)
                publish("loading", 0, len(bars), {"data_source": source})
                probs = None
                if spec.uses_model:
                    probs = await self._predictions(symbol, bars[0].ts_ms, bars[-1].ts_ms)
                    if not probs:
                        raise ValueError(
                            "strategy uses p_up/p_down but no persisted predictions cover this window"
                        )

                def on_progress(i: int, n: int) -> None:
                    loop.call_soon_threadsafe(publish, "running", i, n)

                outcome: BacktestOutcome = await asyncio.to_thread(
                    run_backtest,
                    bars,
                    spec,
                    initial_capital=float(req["initial_capital"]),
                    commission_bps=float(req["commission_bps"]),
                    slippage_bps=float(req["slippage_bps"]),
                    probs_by_ts=probs,
                    progress=on_progress,
                )
                await self._persist(result_id, outcome, source, "completed")
            publish("completed", outcome.n_bars, outcome.n_bars, {"metrics": outcome.metrics})
        except asyncio.CancelledError:
            await self._fail(result_id, "the server shut down during this backtest")
            raise
        except Exception as exc:
            logger.exception("backtest %d failed", result_id)
            await self._fail(result_id, str(exc))
            publish("failed", 0, 0, {"error": str(exc)})

    async def _set_status(self, result_id: int, status: str) -> None:
        async with self._sf() as session:
            row = await session.get(BacktestResult, result_id)
            if row is not None:
                row.status = status
                await session.commit()

    async def _persist(self, result_id: int, o: BacktestOutcome, source: str, status: str) -> None:
        m = o.metrics
        async with self._sf() as session:
            row = await session.get(BacktestResult, result_id)
            if row is None:
                return
            row.status = status
            row.data_source = source
            row.final_capital = m["final_capital"]
            row.total_pnl = m["total_pnl"]
            row.total_pnl_pct = m["total_pnl_pct"]
            row.total_trades = m["total_trades"]
            row.win_rate = m["win_rate"]
            row.max_drawdown_pct = m["max_drawdown_pct"]
            row.sharpe_ratio = m["sharpe_ratio"]
            row.sortino_ratio = m["sortino_ratio"]
            row.profit_factor = m["profit_factor"] if m["profit_factor"] != float("inf") else 999.0
            row.exposure_pct = m["exposure_pct"]
            row.trades_json = o.trades
            row.equity_curve_json = _thin(o.equity_curve, 2_000)
            row.start_time = from_ms(o.start_ms)
            row.end_time = from_ms(o.end_ms)
            await session.commit()

    async def _fail(self, result_id: int, error: str) -> None:
        async with self._sf() as session:
            row = await session.get(BacktestResult, result_id)
            if row is not None:
                row.status = "failed"
                row.trades_json = [{"error": error[:500]}]
                await session.commit()


def _thin(curve: Sequence[list[float]], max_points: int) -> list[list[float]]:
    if len(curve) <= max_points:
        return list(curve)
    step = len(curve) / max_points
    out = [curve[int(i * step)] for i in range(max_points)]
    out[-1] = curve[-1]
    return out
