"""
Auth utilities
==============

Password hashing with `bcrypt` directly (passlib is unmaintained and breaks on
bcrypt ≥ 4.1) and JWTs with `PyJWT` (python-jose has open CVEs).

Reads are public. Mutations depend on `require_writer`: when
`MUTATIONS_REQUIRE_AUTH` is on (production by default) the request must carry
`Authorization: Bearer <ADMIN_TOKEN>` (compared in constant time) or an active
user's JWT from `/auth/login`.
"""

from __future__ import annotations

import hmac
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from algoviz.config import settings
from algoviz.core.time import utcnow
from algoviz.db import DbSession
from algoviz.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# bcrypt silently truncates at 72 bytes; refuse rather than hash a prefix.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        raise ValueError("password exceeds 72 bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    raw = plain.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode("ascii"))
    except ValueError:  # malformed hash
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    now = utcnow()
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": subject, "iat": now, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Return the subject or None if the token is invalid/expired."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None


async def get_current_user(
    db: DbSession,
    token: str | None = Depends(oauth2_scheme),
) -> User | None:
    """Resolve the bearer token to a user; None when unauthenticated."""
    if token is None:
        return None
    username = decode_access_token(token)
    if username is None:
        return None
    user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def require_writer(db: DbSession, token: str | None = Depends(oauth2_scheme)) -> None:
    """Gate for every mutation: open for a local operator, a bearer credential otherwise."""
    if not settings.mutations_require_auth:
        return
    admin = settings.ADMIN_TOKEN
    if token and admin and hmac.compare_digest(token.encode(), admin.encode()):
        return
    if token and await get_current_user(db, token) is not None:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Changes need the admin token or a signed-in user (Authorization: Bearer …)",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
