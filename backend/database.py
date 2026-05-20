"""
AlgoViz Backend — Database Setup
==================================

Async SQLAlchemy engine + session factory for SQLite (aiosqlite).
Upgradeable to PostgreSQL by changing DATABASE_URL.
"""

import logging
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from config import settings

logger = logging.getLogger("algoviz.db")


# ── Engine ───────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Disable SQL echo in production
    connect_args={"check_same_thread": False},  # SQLite-specific
    pool_pre_ping=True,
)

# ── Session Factory ──────────────────────────────────────────────────
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Model ───────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ── Dependency ───────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """FastAPI dependency — provides a database session per request."""
    session = async_session()
    try:
        yield session
        await session.commit()
    except Exception as e:
        logger.error(f"DB session error: {e}")
        await session.rollback()
        raise
    finally:
        await session.close()


# ── Init ─────────────────────────────────────────────────────────────
async def init_db():
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def close_db():
    """Dispose engine on shutdown."""
    await engine.dispose()
