"""
Triple-barrier labelling (López de Prado)
=========================================

For the bar at index `i`, look ahead up to `horizon` bars. The label is the
first barrier touched by the mid-price path:

    up   (2) — mid rises by ≥ +barrier
    down (0) — mid falls by ≥ −barrier
    flat (1) — neither within the horizon (vertical barrier)

The barrier is **volatility-scaled**: `k · σ_1s · √horizon`, i.e. k times the
expected move over the horizon given the bar's current volatility, with an
absolute floor so a dead-flat market still needs a real move to count.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

CLASS_DOWN, CLASS_FLAT, CLASS_UP = 0, 1, 2
CLASS_NAMES: tuple[str, ...] = ("down", "flat", "up")


@dataclass(slots=True)
class Label:
    cls: int
    realised_bps: float  # move at the touch (or at the horizon)
    bars_to_touch: int  # horizon if the vertical barrier was hit
    barrier_bps: float


def barrier_bps(
    volatility_bps_per_min: float | None, horizon_s: int, k: float, floor_bps: float
) -> float:
    """Expected |move| over the horizon scaled by k, floored."""
    v = volatility_bps_per_min if volatility_bps_per_min and volatility_bps_per_min > 0 else 0.0
    expected = k * v * math.sqrt(horizon_s / 60.0)
    return max(expected, floor_bps)


def triple_barrier(
    closes: Sequence[float],
    i: int,
    horizon: int,
    barrier: float,
) -> Label | None:
    """Label bar `i` using closes[i+1 .. i+horizon]. None if the path is incomplete."""
    if i + horizon >= len(closes) or closes[i] <= 0:
        return None
    c0 = closes[i]
    up, dn = barrier, -barrier
    for j in range(1, horizon + 1):
        r = (closes[i + j] / c0 - 1.0) * 10_000
        if r >= up:
            return Label(CLASS_UP, r, j, barrier)
        if r <= dn:
            return Label(CLASS_DOWN, r, j, barrier)
    r = (closes[i + horizon] / c0 - 1.0) * 10_000
    return Label(CLASS_FLAT, r, horizon, barrier)


def realised_class(closes: Sequence[float], i: int, horizon: int, barrier: float) -> str | None:
    lab = triple_barrier(closes, i, horizon, barrier)
    return CLASS_NAMES[lab.cls] if lab else None
