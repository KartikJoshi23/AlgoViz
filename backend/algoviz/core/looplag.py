"""
Event-loop lag
==============

The whole server — market feed, WebSocket fan-out, REST — shares one asyncio
loop, so the loop's responsiveness *is* the service's health. A sampler task
sleeps for a fixed interval and records how late it wakes up; the recent
distribution drives `/health/ready`, `/system/metrics` and the "degraded"
status.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from typing import Any

import numpy as np


class LoopLagMonitor:
    def __init__(self, interval_s: float = 0.1, window: int = 600) -> None:
        self.interval_s = interval_s
        self._samples: deque[float] = deque(maxlen=window)  # seconds late, most recent last
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="loop-lag")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            t0 = loop.time()
            await asyncio.sleep(self.interval_s)
            self.record(loop.time() - t0 - self.interval_s)

    def record(self, late_s: float) -> None:
        self._samples.append(max(late_s, 0.0))

    def p99_ms(self) -> float | None:
        if not self._samples:
            return None
        return float(np.percentile(np.fromiter(self._samples, float), 99) * 1000)

    def stats(self) -> dict[str, Any]:
        if not self._samples:
            return {"samples": 0, "window_s": 0.0}
        arr = np.fromiter(self._samples, float) * 1000
        return {
            "samples": len(arr),
            "window_s": round(len(arr) * self.interval_s, 1),
            "current_ms": round(float(arr[-1]), 2),
            "p50_ms": round(float(np.percentile(arr, 50)), 2),
            "p99_ms": round(float(np.percentile(arr, 99)), 2),
            "max_ms": round(float(arr.max()), 2),
        }


loop_lag = LoopLagMonitor()
