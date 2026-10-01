"""
Adaptive baselines
==================

Every raw feature gets a fast and a slow EWMA (mean + std). z-scores are
computed against the **slow** baseline ("how unusual is this vs. the last
~15 minutes?") and are `None` until the baseline has seen `warmup_s` of data,
so the UI can show *calibrating* rather than a spurious number.
"""

from __future__ import annotations

from algoviz.market.ring import Ewm


class Baseline:
    __slots__ = ("_first_ms", "_warmup_ms", "fast", "slow")

    def __init__(self, fast_halflife_s: float, slow_halflife_s: float, warmup_s: float) -> None:
        self.fast = Ewm(fast_halflife_s)
        self.slow = Ewm(slow_halflife_s)
        self._warmup_ms = int(warmup_s * 1000)
        self._first_ms: int | None = None

    def update(self, ts_ms: int, x: float) -> None:
        if self._first_ms is None:
            self._first_ms = ts_ms
        self.fast.update(ts_ms, x)
        self.slow.update(ts_ms, x)

    def warmed_up(self, now_ms: int) -> bool:
        return self._first_ms is not None and now_ms - self._first_ms >= self._warmup_ms

    def z(self, x: float, now_ms: int, floor_abs: float, floor_rel: float = 0.0) -> float | None:
        """
        z against the slow baseline. The std floor is max(abs, rel·|mean|): an absolute
        floor alone is meaningless across symbols whose scales differ by 1000× (BTC's
        spread is 0.001 bps; a 0.05 bps floor would pin its z at zero forever).
        """
        if not self.warmed_up(now_ms):
            return None
        floor = max(floor_abs, floor_rel * abs(self.slow.mean))
        return self.slow.z(x, floor=floor)

    @property
    def mean(self) -> float:
        return self.slow.mean

    @property
    def std(self) -> float:
        return self.slow.std


Floor = tuple[float, float]  # (absolute, relative-to-|mean|)


class BaselineSet:
    """Named baselines with per-feature std floors (so a dead-flat series can't blow z up)."""

    def __init__(
        self,
        names_and_floors: dict[str, Floor],
        fast_halflife_s: float,
        slow_halflife_s: float,
        warmup_s: float,
    ) -> None:
        self._floors = names_and_floors
        self._b = {
            n: Baseline(fast_halflife_s, slow_halflife_s, warmup_s) for n in names_and_floors
        }

    def update(self, ts_ms: int, values: dict[str, float | None]) -> None:
        for name, v in values.items():
            if v is not None and name in self._b:
                self._b[name].update(ts_ms, v)

    def z(self, name: str, x: float | None, now_ms: int) -> float | None:
        if x is None:
            return None
        floor_abs, floor_rel = self._floors[name]
        return self._b[name].z(x, now_ms, floor_abs, floor_rel)

    def mean(self, name: str) -> float:
        return self._b[name].mean

    def std(self, name: str) -> float:
        return self._b[name].std

    def warmed_up(self, now_ms: int) -> bool:
        return all(b.warmed_up(now_ms) for b in self._b.values())
