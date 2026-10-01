"""
Single-user mode
================

Until multi-user auth is enforced on CRUD routes, strategies and alert rules
belong to a `default` user. It is created once at startup (`ensure_default_user`,
after migrations) with a random password hashed off the event loop, so
requests only ever read it: no bcrypt on the request path and no race between
two first requests both trying to create it.
"""

from __future__ import annotations

import asyncio
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algoviz.core.auth import hash_password
from algoviz.models import User

DEFAULT_USERNAME = "default"

_create_lock = asyncio.Lock()


async def ensure_default_user(sf: async_sessionmaker[AsyncSession]) -> None:
    """Create the default user if it does not exist (committed in its own transaction)."""
    async with _create_lock, sf() as session:
        exists = (
            await session.execute(select(User.id).where(User.username == DEFAULT_USERNAME))
        ).scalar_one_or_none()
        if exists is not None:
            return
        hashed = await asyncio.to_thread(hash_password, secrets.token_urlsafe(24))
        session.add(User(username=DEFAULT_USERNAME, hashed_password=hashed, is_admin=True))
        await session.commit()


async def get_or_create_default_user(db: AsyncSession) -> User:
    user = (
        await db.execute(select(User).where(User.username == DEFAULT_USERNAME))
    ).scalar_one_or_none()
    if user is None:  # only if startup was skipped (e.g. a test app without the lifespan)
        from algoviz.db import async_session

        await ensure_default_user(async_session)
        user = (
            await db.execute(select(User).where(User.username == DEFAULT_USERNAME))
        ).scalar_one()
    return user
