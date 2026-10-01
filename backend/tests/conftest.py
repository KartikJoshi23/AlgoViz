"""
Test fixtures
=============

- Settings are overridden through environment variables *before* `algoviz`
  is imported: isolated SQLite file per session, **synthetic** market source
  (no network), test environment.
- One app + one HTTP client per session; the lifespan runs migrations and
  starts the synthetic engine, so market/analytics endpoints serve real data.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from threadpoolctl import threadpool_limits

_TMP = Path(tempfile.mkdtemp(prefix="algoviz-test-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "MARKET_AUTOSTART": "true",
        "DATA_SOURCE": "synthetic",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}",
        "ML_MODEL_DIR": str(_TMP / "models"),
        "LOG_LEVEL": "WARNING",
        "RATE_LIMIT_RPM": "1000",
        "BACKTEST_MIN_BARS": "50",
        "BACKTEST_SYNTHETIC_BARS": "300",
    }
)

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from algoviz.core.workers import default_threads  # noqa: E402
from algoviz.main import create_app  # noqa: E402


@pytest.fixture(scope="module")
def capped_threads() -> Iterator[None]:
    """
    For modules that train in-process: the training worker's thread cap, since
    unbounded OpenMP oversubscribes the cores on small data sets and runs several
    times slower. Module-scoped on purpose: held for the whole session, it hangs
    the engine test on Windows, whose inference thread sets its own OpenMP limit.
    """
    with threadpool_limits(default_threads()):
        yield


@pytest.fixture(scope="session")
async def app() -> AsyncIterator[FastAPI]:
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # let the synthetic engine sync its book and close a few bars
        for _ in range(60):
            r = await ac.get("/api/v1/market/stats")
            st = r.json()["symbols"]["BTCUSDT"]
            if st["book"]["state"] == "synced" and st["bars_closed"] >= 2:
                break
            await asyncio.sleep(0.1)
        yield ac
