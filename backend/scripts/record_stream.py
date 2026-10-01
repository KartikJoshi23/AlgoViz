"""
Record a live Binance stream to an NDJSON file for replay and tests.

    python scripts/record_stream.py --symbol BTCUSDT --seconds 30 --out data/recordings/btcusdt.ndjson.gz

The recording starts with a REST depth snapshot, followed by every raw
combined-stream message (trades + diff depth) with its receive timestamp.
Any further snapshots the live book requests are recorded in sequence too, so
a replay reproduces the exact sync behaviour. Output is gzip-compressed when
the path ends in `.gz`.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import time
from pathlib import Path
from typing import IO

from algoviz.config import settings
from algoviz.market.binance import BinanceSource
from algoviz.market.events import DepthSnapshotEvent, MarketEvent


def _open(path: Path) -> IO[bytes]:
    path.parent.mkdir(parents=True, exist_ok=True)
    return gzip.open(path, "wb") if str(path).endswith(".gz") else open(path, "wb")


async def record(symbol: str, seconds: float, out: Path) -> int:
    source = BinanceSource(
        symbol, ws_hosts=settings.BINANCE_WS_HOSTS, rest_hosts=settings.BINANCE_REST_HOSTS
    )
    fh = _open(out)
    n = 0
    snapshot_pending = True

    def write(kind: str, data: object) -> None:
        nonlocal n
        rec = {"ts": int(time.time() * 1000), "kind": kind, "data": data}
        fh.write(json.dumps(rec, separators=(",", ":")).encode() + b"\n")
        n += 1

    def tap(raw: object) -> None:
        if isinstance(raw, tuple) and raw[0] == "snapshot":
            write("snapshot", json.loads(raw[1]))
        elif isinstance(raw, bytes | str):
            write("ws", json.loads(raw))

    def emit(ev: MarketEvent) -> None:
        nonlocal snapshot_pending
        if isinstance(ev, DepthSnapshotEvent):
            snapshot_pending = False

    source.raw_tap = tap
    task = asyncio.create_task(source.run(emit))
    try:
        # wait for the stream, then request the opening snapshot
        while source.status != "connected":  # noqa: ASYNC110 — status is a plain attribute
            await asyncio.sleep(0.05)
        await source.request_snapshot()
        deadline = time.monotonic() + seconds
        await asyncio.sleep(max(deadline - time.monotonic(), 0))
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        fh.close()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default=settings.default_symbol)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=Path("data/recordings") / "stream.ndjson.gz")
    args = ap.parse_args()
    n = asyncio.run(record(args.symbol.upper(), args.seconds, args.out))
    size = args.out.stat().st_size
    print(f"recorded {n} records to {args.out} ({size / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
