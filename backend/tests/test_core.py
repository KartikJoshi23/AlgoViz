"""Unit tests — auth primitives, config guards, middleware, legacy rules."""

from __future__ import annotations

from datetime import timedelta

import pytest

from algoviz.config import DEV_SECRET_KEY, Settings
from algoviz.core.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# ── Passwords / tokens ────────────────────────────────────────────


def test_password_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$2b$")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)
    assert not verify_password("anything", "not-a-hash")


def test_password_over_72_bytes_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("x" * 73)
    assert not verify_password("x" * 73, hash_password("x" * 72))


def test_token_roundtrip_and_expiry() -> None:
    assert decode_access_token(create_access_token("alice")) == "alice"
    expired = create_access_token("alice", expires_delta=timedelta(seconds=-1))
    assert decode_access_token(expired) is None
    assert decode_access_token("garbage") is None


# ── Config guards ─────────────────────────────────────────────────


def test_production_refuses_dev_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ENVIRONMENT="production", SECRET_KEY=DEV_SECRET_KEY, _env_file=None)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="ADMIN_TOKEN"):
        Settings(ENVIRONMENT="production", SECRET_KEY="x" * 32, _env_file=None)  # type: ignore[call-arg]
    s = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 32, ADMIN_TOKEN="t" * 32, _env_file=None
    )  # type: ignore[call-arg]
    assert s.is_production and s.mutations_require_auth and not s.registration_open


def test_hosted_postgres_urls_get_the_async_driver() -> None:
    for given in ("postgres://u:p@db:5432/algoviz", "postgresql://u:p@db:5432/algoviz"):
        s = Settings(DATABASE_URL=given, _env_file=None)  # type: ignore[call-arg]
        assert s.DATABASE_URL == "postgresql+asyncpg://u:p@db:5432/algoviz"
    local = "sqlite+aiosqlite:///./data/x.db"
    assert Settings(DATABASE_URL=local, _env_file=None).DATABASE_URL == local  # type: ignore[call-arg]


def test_symbols_must_be_allowlisted() -> None:
    with pytest.raises(ValueError, match="SYMBOL_ALLOWLIST"):
        Settings(SYMBOLS=["DOGEUSDT"], _env_file=None)  # type: ignore[call-arg]
    s = Settings(SYMBOLS=["ethusdt"], _env_file=None)  # type: ignore[call-arg]
    assert s.SYMBOLS == ["ETHUSDT"]


def test_replay_requires_file() -> None:
    with pytest.raises(ValueError, match="REPLAY_FILE"):
        Settings(DATA_SOURCE="replay", _env_file=None)  # type: ignore[call-arg]
