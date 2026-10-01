"""
Database
========

Async SQLAlchemy engine + session factory. SQLite by default (WAL mode for
concurrent reads during the 1 Hz snapshot writer); Postgres is a
`DATABASE_URL` change. Schema is managed by Alembic (`alembic upgrade head`);
`init_db()` runs migrations at startup so a fresh checkout just works.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from alembic.config import Config as AlembicConfig
from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from alembic import command
from algoviz.config import BASE_DIR, settings

logger = logging.getLogger("algoviz.db")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def create_engine_from_settings(url: str | None = None) -> AsyncEngine:
    url = url or settings.DATABASE_URL
    kwargs: dict[str, object] = {"echo": settings.DB_ECHO, "pool_pre_ping": True}
    if _is_sqlite(url):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_async_engine(url, **kwargs)

    if _is_sqlite(url):

        @event.listens_for(eng.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

    return eng


engine: AsyncEngine = create_engine_from_settings()
async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request, commit on success. Use it through `DbSession`."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# `scope="function"` runs the commit *before* the response is sent. The default
# (request scope) commits afterwards, so a client that re-reads right after a
# 2xx could see the old state — and a commit that failed was already reported
# as a success.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]


def page(rows: list[Any], limit: int) -> dict[str, Any]:
    """A keyset page from `limit + 1` rows ordered by id, newest first: the extra row only says more exist."""
    items = rows[:limit]
    more = len(rows) > limit and bool(items)
    last = items[-1] if more else None
    return {
        "items": items,
        "next_before": (last["id"] if isinstance(last, dict) else last.id)
        if last is not None
        else None,
    }


def _alembic_config(url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


def run_migrations(url: str | None = None) -> None:
    """Apply Alembic migrations to head (synchronous; call via `to_thread`)."""
    url = url or settings.DATABASE_URL
    command.upgrade(_alembic_config(url), "head")


async def init_db() -> None:
    import asyncio

    if _is_sqlite(settings.DATABASE_URL) and ":memory:" in settings.DATABASE_URL:
        # In-memory DBs are per-connection; migrations can't target them. Tests
        # create tables directly.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return
    await asyncio.to_thread(run_migrations)
    logger.info("database migrated to head (%s)", _redact(settings.DATABASE_URL))


async def close_db() -> None:
    await engine.dispose()


def _redact(url: str) -> str:
    if "@" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url if not _is_sqlite(url) else Path(url.split("///")[-1]).name


__all__ = [
    "Base",
    "DbSession",
    "async_session",
    "close_db",
    "create_engine_from_settings",
    "engine",
    "get_db",
    "init_db",
    "run_migrations",
]
