"""
Run the edge study (implementation-plan §11 W5, §12; `algoviz/ml/study.py`).

    python scripts/ml_study.py                          # exploratory: bars before the freeze
    python scripts/ml_study.py --out ../docs/edge-study.md
    python scripts/ml_study.py --decide                 # deciding: bars from the freeze on
    python scripts/ml_study.py --quick                  # three label definitions, not the grid

Bars come from the database the server uses for the source and from the export
files under `--exports` (`scripts/export_bars.py`), one per open time. The
protocol (`docs/edge-study-protocol.md`) was frozen at `study.FREEZE_MS`.

Without `--decide` the study runs on the bars from before the freeze: they shaped
the protocol, so the run explores and decides nothing. With it, the study runs on
the bars from the freeze on, and only once there are at least seven days of them:
a run on fewer would look at the deciding data before it is complete. The full
grid refits as served, about 2,650 times on a week of bars (about 70 minutes).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PROTOCOL = BACKEND.parent / "docs" / "edge-study-protocol.md"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--source", default="live", choices=["live", "synthetic"])
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--exports", type=Path, default=BACKEND / "data" / "exports")
    ap.add_argument("--out", type=Path, help="also write the Markdown report here")
    ap.add_argument(
        "--decide", action="store_true", help="the deciding run, on bars after the freeze"
    )
    ap.add_argument(
        "--quick", action="store_true", help="the served label and two longer ones, not the grid"
    )
    args = ap.parse_args()
    # Settings resolve the database from the data source: set it before the app is imported.
    os.environ["DATA_SOURCE"] = args.source
    os.environ.setdefault("MARKET_AUTOSTART", "false")
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    from algoviz.config import settings
    from algoviz.db import async_session
    from algoviz.market.bars import Bar
    from algoviz.market.persistence import iter_bars, read_bar_exports
    from algoviz.ml.study import (
        MIN_DAYS,
        ConfigResult,
        LabelSpec,
        render,
        run_study,
        split_at_freeze,
    )

    async def from_db() -> list[Bar]:
        bars: list[Bar] = []
        pages = iter_bars(async_session, args.symbol, source=args.source, start_ms=0, limit=10**9)
        async for page in pages:
            bars.extend(page)
        return bars

    files = sorted(args.exports.glob(f"bars-{args.symbol}-{args.source}-*.ndjson.gz"))
    merged = {b.ts_ms: b for b in read_bar_exports(files)}
    merged.update({b.ts_ms: b for b in asyncio.run(from_db())})
    before, after = split_at_freeze([merged[t] for t in sorted(merged)])
    days_after = len(after) / 86_400
    print(
        f"{len(before):,} bars before the freeze, {len(after):,} from it on ({days_after:.2f} "
        f"days), from the database and {len(files)} export file(s)",
        file=sys.stderr,
    )
    if args.decide and days_after < MIN_DAYS:
        print(
            f"not deciding: {days_after:.2f} days of bars from the freeze on, the rule needs "
            f"{MIN_DAYS:g}; the deciding data stay unexamined until then"
        )
        return 1
    bars = after if args.decide else before
    if not bars:
        print(f"no {args.source} bars for {args.symbol}")
        return 1
    protocol = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()[:16]

    started = time.monotonic()

    def progress(r: ConfigResult) -> None:
        edge = f"{r.mean_edge:+.4f}" if r.quarters else "too few samples"
        print(f"  {time.monotonic() - started:6.0f} s  {r.name}: {edge}", file=sys.stderr)

    served = LabelSpec(settings.ML_HORIZON_S, settings.ML_BARRIER_K, settings.ML_MIN_BARRIER_BPS)
    specs = [served, LabelSpec(30, 1.0, 1.0), LabelSpec(60, 1.0, 2.0)] if args.quick else None
    report = run_study(
        bars, settings, deciding=args.decide, specs=specs, protocol=protocol, progress=progress
    )
    text = render(report)
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}", file=sys.stderr)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
