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
import inspect
import io
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

# An async test still running after this long has hung (none takes a minute, even under
# coverage). It is failed with every asyncio task's stack in its report: in a hang the
# thread stacks show only idle threads, while the task stacks show the await that never
# returns. (pytest's faulthandler_timeout covers synchronous hangs.)
HANG_S = 300.0


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "function", None)):
            item.fixturenames.append("_hang_guard")  # type: ignore[attr-defined]


@pytest.fixture
async def _hang_guard(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()

    def expire() -> None:
        stacks = io.StringIO()
        for task in asyncio.all_tasks(loop):
            task.print_stack(file=stacks)
        request.node.add_report_section("call", "asyncio tasks at the hang", stacks.getvalue())
        for task in asyncio.all_tasks(loop):
            if getattr(task.get_coro(), "__name__", None) == request.node.originalname:
                task.cancel(f"still running after {HANG_S:.0f} s")

    timer = loop.call_later(HANG_S, expire)
    yield
    timer.cancel()


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
