"""
Export persisted bars to gzipped NDJSON, so they outlive the database's retention.

    python scripts/export_bars.py                       # live BTCUSDT bars
    python scripts/export_bars.py --source synthetic

Reads the database the server uses for that source (the data source picks it,
as it does for the server) and writes one file per run under `data/exports/`,
named by symbol, source and the span it covers. The edge study
(`scripts/ml_study.py`) reads these beside the database and keeps one bar per
open time, so overlapping exports are harmless.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _stamp(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y%m%dT%H%M%S")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--source", default="live", choices=["live", "synthetic"])
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--out", type=Path, default=BACKEND / "data" / "exports")
    args = ap.parse_args()
    # Settings resolve the database from the data source: set it before the app is imported.
    os.environ["DATA_SOURCE"] = args.source
    os.environ.setdefault("MARKET_AUTOSTART", "false")
    from algoviz.db import async_session
    from algoviz.market.bars import Bar
    from algoviz.market.persistence import iter_bars, write_bar_export

    async def collect() -> list[Bar]:
        bars: list[Bar] = []
        pages = iter_bars(async_session, args.symbol, source=args.source, start_ms=0, limit=10**9)
        async for page in pages:
            bars.extend(page)
        return bars

    bars = asyncio.run(collect())
    if not bars:
        print(f"no {args.source} bars for {args.symbol}")
        return 1
    span = f"{_stamp(bars[0].ts_ms)}-{_stamp(bars[-1].ts_ms)}"
    path = args.out / f"bars-{args.symbol}-{args.source}-{span}.ndjson.gz"
    write_bar_export(bars, path)
    print(f"wrote {path} ({len(bars)} bars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
