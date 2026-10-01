"""Registration, login, current user."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from algoviz.config import settings
from algoviz.core.auth import (
    create_access_token,
    hash_password,
    oauth2_scheme,
    require_user,
    require_writer,
    verify_password,
)
from algoviz.db import DbSession
from algoviz.models import User
from algoviz.schemas.rest import (
    AccessResponse,
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register",
)
async def register(data: UserCreate, db: DbSession) -> User:
    if not settings.registration_open:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled on this server")
    exists = (
        await db.execute(select(User).where(User.username == data.username))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    # bcrypt costs ~0.2 s of CPU: never on the event loop that also carries the market feed.
    hashed = await asyncio.to_thread(hash_password, data.password)
    user = User(username=data.username, email=data.email, hashed_password=hashed)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse, summary="Login → JWT")
async def login(data: LoginRequest, db: DbSession) -> TokenResponse:
    user = (
        await db.execute(select(User).where(User.username == data.username))
    ).scalar_one_or_none()
    if user is None or not await asyncio.to_thread(
        verify_password, data.password, user.hashed_password
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return TokenResponse(
        access_token=create_access_token(user.username), user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse, summary="Current user")
async def me(user: User = Depends(require_user)) -> User:
    return user


@router.get("/access", response_model=AccessResponse, summary="May this request make changes?")
async def access(db: DbSession, token: str | None = Depends(oauth2_scheme)) -> AccessResponse:
    """Whether this server gates changes, and whether the bearer sent here would pass."""
    try:
        await require_writer(db, token)
        allowed = True
    except HTTPException:
        allowed = False
    return AccessResponse(writes_require_auth=settings.mutations_require_auth, can_write=allowed)
