"""
Backtest engine
===============

Bar-by-bar, no look-ahead: a decision made on bar *t* is filled at bar
*t+1*'s close (mid) ± slippage, commission charged both ways. One position at
a time; stops/targets are checked against the high/low of the bars *after*
the fill bar; `max_hold_s` and the declarative `exit` condition are checked
at close. Position size is a percentage of *current* equity.

Evaluation context per bar = bar fields + extras + (p_up, p_down) if provided
+ position state (`bars_held`, `position`, `unrealised_bps`). The trend is
recomputed from the closes with the live detector's statistic, so history
recorded before trends were stored can still be tested on it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from algoviz.backtest.metrics import summarise
from algoviz.backtest.strategy import StrategySpec
from algoviz.market.bars import SESSION_GAP_MS, Bar
from algoviz.market.regime import TrendTracker

Progress = Callable[[int, int], None]


@dataclass(slots=True)
class BacktestOutcome:
    metrics: dict[str, Any]
    trades: list[dict[str, Any]]
    equity_curve: list[list[float]]  # [ts_ms, equity, drawdown_pct]
    n_bars: int
    start_ms: int
    end_ms: int
    spec: dict[str, Any] = field(default_factory=dict)


def bar_context(bar: Bar, probs: Mapping[str, float] | None = None) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "last_price": bar.last_price,
        "mid": bar.close,
        "microprice": bar.microprice,
        "microprice_dev_bps": (bar.extra or {}).get("microprice_dev_bps"),
        "vwap": bar.vwap,
        "price_vs_vwap_bps": ((bar.close - bar.vwap) / bar.vwap * 10_000) if bar.vwap else None,
        "spread_bps": bar.spread_bps,
        "imbalance_l1": bar.imbalance,
        "imbalance_w": bar.imbalance_w,
        "liquidity_5bps": bar.liquidity_5bps,
        "liquidity_10bps": bar.liquidity_10bps,
        "book_slope_bid": bar.book_slope,
        "book_slope_ask": bar.book_slope,
        "ofi_1s": bar.ofi,
        "ofi_5s": (bar.extra or {}).get("ofi_5s"),
        "ofi_30s": (bar.extra or {}).get("ofi_30s"),
        "velocity": bar.velocity,
        "buy_pressure": bar.buy_pressure,
        "volume_30s": None,
        "volatility_bps": bar.volatility_bps,
        "spread_z": bar.spread_z,
        "velocity_z": bar.velocity_z,
        "vol_z": bar.vol_z,
        "ofi_z": bar.ofi_z,
        "imbalance_z": bar.imbalance_z,
        "regime": bar.regime,
    }
    if probs:
        ctx["p_up"] = probs.get("p_up")
        ctx["p_down"] = probs.get("p_down")
    return ctx


class _Position:
    __slots__ = ("bars_held", "entry_idx", "entry_price", "entry_ts", "qty", "side")

    def __init__(self, side: int, qty: float, price: float, ts: int, idx: int) -> None:
        self.side = side  # +1 long, −1 short
        self.qty = qty
        self.entry_price = price
        self.entry_ts = ts
        self.entry_idx = idx
        self.bars_held = 0

    def unrealised_bps(self, price: float) -> float:
        return (price / self.entry_price - 1.0) * 10_000 * self.side


def run_backtest(
    bars: Sequence[Bar],
    spec: StrategySpec,
    *,
    initial_capital: float = 10_000.0,
    commission_bps: float = 1.0,
    slippage_bps: float = 0.5,
    probs_by_ts: Mapping[int, Mapping[str, float]] | None = None,
    progress: Progress | None = None,
) -> BacktestOutcome:
    n = len(bars)
    if n < 3:
        raise ValueError("need at least 3 bars")
    equity = initial_capital
    cash = initial_capital
    pos: _Position | None = None
    trades: list[dict[str, Any]] = []
    curve: list[list[float]] = []
    peak = initial_capital
    bars_in_pos = 0
    cooldown_until_ms = 0
    pending: int | None = None  # +1 / −1 decided on the previous bar, filled at this bar's close
    pending_exit: str | None = None
    trend = TrendTracker()
    prev: Bar | None = None

    fee = commission_bps / 10_000
    slip = slippage_bps / 10_000

    def fill_price(price: float, side_sign: int) -> float:
        # buying pays up, selling receives less
        return price * (1 + slip * side_sign)

    def close_position(p: _Position, price: float, ts: int, reason: str) -> None:
        nonlocal cash, equity, pos
        exit_px = fill_price(price, -p.side)
        gross = (exit_px - p.entry_price) * p.qty * p.side
        costs = (p.entry_price + exit_px) * p.qty * fee
        pnl = gross - costs
        cash += pnl
        equity = cash
        trades.append(
            {
                "side": "long" if p.side > 0 else "short",
                "entry_ts": p.entry_ts,
                "exit_ts": ts,
                "entry_price": round(p.entry_price, 6),
                "exit_price": round(exit_px, 6),
                "qty": round(p.qty, 8),
                "pnl": round(pnl, 6),
                "pnl_bps": round((exit_px / p.entry_price - 1) * 10_000 * p.side, 3),
                "costs": round(costs, 6),
                "hold_s": round((ts - p.entry_ts) / 1000, 1),
                "reason": reason,
            }
        )
        pos = None

    for i, bar in enumerate(bars):
        ts = bar.ts_ms
        price = bar.close
        if price <= 0:
            continue

        # 1) fills decided on the previous bar
        if pos is not None and pending_exit is not None:
            close_position(pos, price, ts, pending_exit)
            pending_exit = None
            cooldown_until_ms = ts + spec.cooldown_s * 1000
        if pos is None and pending is not None and ts >= cooldown_until_ms:
            notional = equity * spec.size_pct / 100.0
            px = fill_price(price, pending)
            qty = notional / px
            if qty > 0:
                pos = _Position(pending, qty, px, ts, i)
        pending = None

        # 2) intrabar stops / targets on the open position (conservative: stop first).
        #    Not on the fill bar: the fill is at its close, so its high/low printed
        #    *before* the position existed.
        if pos is not None and pos.entry_idx < i:
            pos.bars_held = i - pos.entry_idx
            lo_bps = (bar.low / pos.entry_price - 1) * 10_000 * pos.side
            hi_bps = (bar.high / pos.entry_price - 1) * 10_000 * pos.side
            worst, best = min(lo_bps, hi_bps), max(lo_bps, hi_bps)
            if spec.stop_loss_bps is not None and worst <= -spec.stop_loss_bps:
                stop_px = pos.entry_price * (1 - spec.stop_loss_bps / 10_000 * pos.side)
                close_position(pos, stop_px, ts, "stop_loss")
                cooldown_until_ms = ts + spec.cooldown_s * 1000
            elif spec.take_profit_bps is not None and best >= spec.take_profit_bps:
                tp_px = pos.entry_price * (1 + spec.take_profit_bps / 10_000 * pos.side)
                close_position(pos, tp_px, ts, "take_profit")
                cooldown_until_ms = ts + spec.cooldown_s * 1000

        # 3) decisions at close (executed next bar)
        if prev is not None and ts - prev.ts_ms > SESSION_GAP_MS:
            trend.clear()
            prev = None
        trend.push(math.log(price / prev.close) if prev is not None and prev.close > 0 else 0.0)
        prev = bar
        probs = probs_by_ts.get(ts) if probs_by_ts else None
        ctx = bar_context(bar, probs)
        ctx.update(trend=trend.label, regime_direction=math.tanh(trend.t / 2.0))
        if pos is not None:
            ctx.update(
                bars_held=pos.bars_held,
                position=pos.side,
                unrealised_bps=pos.unrealised_bps(price),
            )
            if spec.max_hold_s is not None and (ts - pos.entry_ts) >= spec.max_hold_s * 1000:
                pending_exit = "max_hold"
            elif spec.exit is not None and spec.exit.evaluate(ctx):
                pending_exit = "exit_rule"
        else:
            ctx.update(bars_held=0, position=0, unrealised_bps=0.0)
            if ts >= cooldown_until_ms:
                if (
                    spec.side in ("long", "both")
                    and spec.entry_long
                    and spec.entry_long.evaluate(ctx)
                ):
                    pending = 1
                elif (
                    spec.side in ("short", "both")
                    and spec.entry_short
                    and spec.entry_short.evaluate(ctx)
                ):
                    pending = -1

        # 4) mark to market
        mtm = cash + (pos.qty * (price - pos.entry_price) * pos.side if pos else 0.0)
        equity = mtm
        peak = max(peak, mtm)
        curve.append([float(ts), round(mtm, 4), round((mtm - peak) / peak * 100, 4)])
        if pos is not None:
            bars_in_pos += 1
        if progress and i % 500 == 0:
            progress(i, n)

    # close any open position at the last bar
    if pos is not None:
        close_position(pos, bars[-1].close, bars[-1].ts_ms, "end_of_data")
        curve[-1][1] = round(equity, 4)

    metrics = summarise(
        trades, [int(c[0]) for c in curve], [c[1] for c in curve], initial_capital, bars_in_pos, n
    )
    if progress:
        progress(n, n)
    return BacktestOutcome(
        metrics=metrics,
        trades=trades,
        equity_curve=curve,
        n_bars=n,
        start_ms=bars[0].ts_ms,
        end_ms=bars[-1].ts_ms,
        spec=spec.model_dump(mode="json", by_alias=True),
    )
