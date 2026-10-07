"""
Run the live backend as a long-lived bar collector (the edge study's data, plan §11, E7).

    pythonw scripts/collect_live.py              # Windows: no console, output to the log
    python scripts/collect_live.py --port 8001   # in a console, output stays there

It is the live engine with production's collection settings: bars kept 60 days,
training on one thread, bound to localhost. Without a console (pythonw, a task
started at logon) its output goes to `data/logs/collector.log`, rotated at 20 MB.
While it runs it is the live database's only writer: don't start a second live
backend beside it (their model versions would collide).
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
LOG = BACKEND / "data" / "logs" / "collector.log"
ROTATE_BYTES = 20 * 1024 * 1024

# pythonw has no stdout or stderr, and spawned training processes re-import this file:
# give both streams the log here, before anything writes to them.
TO_LOG = sys.stdout is None
if TO_LOG:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)

os.environ.setdefault("DATA_SOURCE", "live")
os.environ.setdefault("SNAPSHOT_RETENTION_DAYS", "60")
os.environ.setdefault("ML_TRAIN_THREADS", "1")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()
    # uvicorn starts the app (feed, writer, engine) before it binds: check the port first,
    # so a second start beside a running collector exits instead of writing alongside it.
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            print(f"port {args.port} is in use: a collector is already running", flush=True)
            return 0
    if TO_LOG and LOG.stat().st_size > ROTATE_BYTES:
        sys.stdout.close()
        LOG.replace(LOG.with_suffix(".log.1"))
        sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
    os.chdir(BACKEND)
    import uvicorn

    uvicorn.run("algoviz.main:app", host="127.0.0.1", port=args.port, proxy_headers=False)
    return 1  # uvicorn returned: the server stopped, and a supervising task restarts it


if __name__ == "__main__":
    raise SystemExit(main())
