"""
Logging
=======

One `configure_logging()` call at startup. Human-readable in development,
single-line JSON (`LOG_JSON=true`) for production log aggregation.

Warnings and errors are de-duplicated: a record identical to one logged in
the last minute (same logger, level and message) is held back and counted,
and the next one that passes says how many were suppressed. A flapping feed
logs one line a minute instead of one per reconnect.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime

REPEAT_WINDOW_S = 60.0


class RepeatFilter(logging.Filter):
    """Suppress a warning or error identical to one passed in the last `window_s` seconds."""

    def __init__(self, window_s: float = REPEAT_WINDOW_S) -> None:
        super().__init__()
        self.window_s = window_s
        self._seen: dict[
            tuple[str, int, str], tuple[float, int]
        ] = {}  # key → (passed at, suppressed)

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.WARNING:
            return True
        key = (record.name, record.levelno, record.getMessage())
        now = time.monotonic()
        passed_at, suppressed = self._seen.get(key, (0.0, 0))
        if now - passed_at < self.window_s:
            self._seen[key] = (passed_at, suppressed + 1)
            return False
        if suppressed:
            record.msg = f"{record.getMessage()} (repeated {suppressed}× in the last {now - passed_at:.0f} s)"
            record.args = None
        self._seen[key] = (now, 0)
        if len(self._seen) > 1024:  # distinct messages only; drop the stalest half
            for k in sorted(self._seen, key=lambda k: self._seen[k][0])[:512]:
                del self._seen[k]
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_TEXT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s"


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    # Windows consoles default to cp1252; never let a log line raise.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_logs else logging.Formatter(_TEXT_FORMAT, datefmt="%H:%M:%S")
    )
    handler.addFilter(RepeatFilter())
    root.addHandler(handler)
    root.setLevel(level)

    # Quieten chatty libraries; our own loggers inherit the root level.
    for noisy in ("uvicorn.access", "websockets", "httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
