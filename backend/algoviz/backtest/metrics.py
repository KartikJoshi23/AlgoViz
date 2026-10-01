"""Backtest performance metrics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

MINUTES_PER_YEAR = 365 * 24 * 60


def resample_equity_1m(ts_ms: Sequence[int], equity: Sequence[float]) -> np.ndarray:
    """Last equity value per 1-minute bucket (so Sharpe isn't computed on 1 s noise)."""
    if not ts_ms:
        return np.asarray([], dtype=float)
    buckets: dict[int, float] = {}
    for t, e in zip(ts_ms, equity, strict=True):
        buckets[t // 60_000] = e
    return np.asarray([buckets[k] for k in sorted(buckets)], dtype=float)


def sharpe_sortino(equity_1m: np.ndarray) -> tuple[float, float]:
    if len(equity_1m) < 3:
        return 0.0, 0.0
    rets = np.diff(equity_1m) / equity_1m[:-1]
    mu, sd = rets.mean(), rets.std(ddof=1) if len(rets) > 1 else 0.0
    sharpe = float(mu / sd * math.sqrt(MINUTES_PER_YEAR)) if sd > 0 else 0.0
    downside = rets[rets < 0]
    dsd = float(np.sqrt((downside**2).mean())) if len(downside) else 0.0
    sortino = float(mu / dsd * math.sqrt(MINUTES_PER_YEAR)) if dsd > 0 else 0.0
    return sharpe, sortino


def max_drawdown_pct(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    arr = np.asarray(equity, dtype=float)
    peaks = np.maximum.accumulate(arr)
    dd = (arr - peaks) / peaks
    return float(-dd.min() * 100)


def summarise(
    trades: list[dict[str, Any]],
    ts_ms: Sequence[int],
    equity: Sequence[float],
    initial_capital: float,
    bars_in_position: int,
    n_bars: int,
) -> dict[str, Any]:
    final = float(equity[-1]) if equity else initial_capital
    pnl = final - initial_capital
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    gross_win = float(sum(wins))
    gross_loss = float(-sum(losses))
    sharpe, sortino = sharpe_sortino(resample_equity_1m(ts_ms, equity))
    return {
        "initial_capital": initial_capital,
        "final_capital": round(final, 4),
        "total_pnl": round(pnl, 4),
        "total_pnl_pct": round(pnl / initial_capital * 100, 4) if initial_capital else 0.0,
        "total_trades": len(trades),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "avg_win": round(gross_win / len(wins), 4) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 4) if losses else 0.0,
        "profit_factor": round(gross_win / gross_loss, 4)
        if gross_loss > 0
        else (float("inf") if gross_win > 0 else 0.0),
        "max_drawdown_pct": round(max_drawdown_pct(equity), 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "exposure_pct": round(bars_in_position / n_bars * 100, 2) if n_bars else 0.0,
        "avg_hold_s": round(float(np.mean([t["hold_s"] for t in trades])), 2) if trades else 0.0,
        "total_costs": round(float(sum(t["costs"] for t in trades)), 4),
    }
