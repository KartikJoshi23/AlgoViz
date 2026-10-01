"""Replay source & full-engine determinism on a recorded Binance fixture."""

from __future__ import annotations

import asyncio
from itertools import pairwise
from pathlib import Path

import pytest

from algoviz.config import Settings
from algoviz.market.events import DepthDiffEvent, DepthSnapshotEvent, MarketEvent, TradeEvent
from algoviz.market.replay import ReplaySource
from algoviz.market.service import SymbolEngine
from algoviz.ws.hub import Hub

FIXTURE = Path(__file__).parent / "fixtures" / "btcusdt-20s.ndjson.gz"
S = "BTCUSDT"
CFG = Settings(_env_file=None)  # type: ignore[call-arg]


async def _run_engine() -> SymbolEngine:
    src = ReplaySource(S, FIXTURE, speed=0, loop=False)
    engine = SymbolEngine(S, CFG, src, Hub(), writer=None, preload=False)
    await engine.start()
    await asyncio.wait_for(src.finished.wait(), timeout=60)
    await asyncio.sleep(0.05)
    await engine.stop()
    return engine


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
async def test_replay_syncs_book_and_builds_bars() -> None:
    e = await _run_engine()
    st = e.stats()
    assert st["book"]["state"] == "synced" and st["book"]["resyncs"] == 0
    assert st["book"]["levels"] > 1000  # a 1000-level snapshot each side, roughly
    assert st["trades"] > 500 and st["diffs"] == 200 and st["dropped_diffs"] < st["diffs"]
    assert 15 <= st["bars_closed"] <= 22  # ~20 s of data
    bars = list(e.bar_ring)
    assert all(b.trade_count >= 0 and b.close > 0 for b in bars)
    assert sum(b.trade_count for b in bars) <= st["trades"]
    ts = [b.ts_ms for b in bars]
    assert ts == sorted(ts) and all(b - a == 1000 for a, b in pairwise(ts))
    snap = e.features.snapshot(e.now_ms())
    assert snap.mid and snap.spread_bps is not None and snap.trade_count_30s > 0
    assert snap.source == "replay"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
async def test_replay_is_deterministic() -> None:
    a = await _run_engine()
    b = await _run_engine()
    rows_a = [bar.compact() for bar in a.bar_ring]
    rows_b = [bar.compact() for bar in b.bar_ring]
    assert rows_a == rows_b and len(rows_a) > 10
    assert a.stats()["events"] == b.stats()["events"]


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
async def test_replay_loop_keeps_time_monotonic_and_resyncs() -> None:
    src = ReplaySource(S, FIXTURE, speed=0, loop=True)
    events: list[MarketEvent] = []
    task = asyncio.create_task(src.run(events.append))
    while src.loops < 2:  # noqa: ASYNC110 — polling a counter the source owns
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    ts = [e.ts_ms for e in events if isinstance(e, TradeEvent | DepthDiffEvent)]
    # Real feeds interleave two streams whose timestamps disagree by a few ms; what must
    # never happen is a large backwards jump (the loop boundary rewinding ~20 s).
    worst_backstep = max((a - b for a, b in pairwise(ts)), default=0)
    assert worst_backstep < 1000, f"timestamps jumped back {worst_backstep} ms"
    assert ts[-1] > ts[0] + 20_000, "second loop must continue forward in time"
    snaps = [e for e in events if isinstance(e, DepthSnapshotEvent)]
    assert len(snaps) >= 2 and snaps[1].ts_ms > snaps[0].ts_ms
    # trade ids keep increasing across the loop, or de-duplicating consumers drop the tape
    tids = [e.trade_id for e in events if isinstance(e, TradeEvent)]
    assert all(b > a for a, b in pairwise(tids)), "trade ids must be strictly increasing"
    assert src.stats()["loops"] >= 1


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
async def test_replay_paces_by_recorded_time() -> None:
    src = ReplaySource(S, FIXTURE, speed=200.0, loop=False)  # 20 s → ~0.1 s
    n = 0

    def emit(_: MarketEvent) -> None:
        nonlocal n
        n += 1

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    await asyncio.wait_for(src.run(emit), timeout=30)
    elapsed = loop.time() - t0
    assert n > 900 and 0.05 < elapsed < 5.0
    assert src.status == "finished"


async def test_replay_missing_file_raises() -> None:
    src = ReplaySource(S, Path("does-not-exist.ndjson"), speed=0)
    with pytest.raises(FileNotFoundError):
        await src.run(lambda _e: None)
