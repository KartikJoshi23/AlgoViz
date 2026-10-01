"""Strategy CRUD + backtest endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algoviz.backtest.strategy import EXAMPLE_SPECS, StrategySpec
from algoviz.config import settings
from algoviz.core.auth import require_writer
from algoviz.core.users import get_or_create_default_user
from algoviz.db import DbSession, page
from algoviz.market.service import market_service
from algoviz.models import BacktestResult, Strategy
from algoviz.schemas.rest import (
    BacktestDetailResponse,
    BacktestPage,
    BacktestRequest,
    BacktestResponse,
    StrategyCreate,
    StrategyExample,
    StrategyResponse,
    StrategyUpdate,
)

router = APIRouter(prefix="/strategies", tags=["Strategies"])

WRITE = [Depends(require_writer)]  # mutations: see core/auth.py


async def _get_strategy(strategy_id: int, db: AsyncSession) -> Strategy:
    strategy = (
        await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    ).scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    return strategy


@router.get("/examples", response_model=list[StrategyExample], summary="Example strategy specs")
async def list_examples() -> list[dict[str, object]]:
    return [
        {"id": k, "config": v, "description": StrategySpec.model_validate(v).describe()}
        for k, v in EXAMPLE_SPECS.items()
    ]


@router.get("", response_model=list[StrategyResponse], summary="List strategies")
async def list_strategies(db: DbSession) -> list[Strategy]:
    user = await get_or_create_default_user(db)
    rows = await db.execute(
        select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.created_at.desc())
    )
    return list(rows.scalars().all())


@router.post(
    "",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create strategy",
    dependencies=WRITE,
)
async def create_strategy(data: StrategyCreate, db: DbSession) -> Strategy:
    user = await get_or_create_default_user(db)
    strategy = Strategy(user_id=user.id, **data.model_dump())
    db.add(strategy)
    await db.flush()
    await db.refresh(strategy)
    return strategy


@router.get("/{strategy_id}", response_model=StrategyResponse, summary="Get strategy")
async def get_strategy(strategy_id: int, db: DbSession) -> Strategy:
    return await _get_strategy(strategy_id, db)


@router.patch(
    "/{strategy_id}", response_model=StrategyResponse, summary="Update strategy", dependencies=WRITE
)
async def update_strategy(strategy_id: int, data: StrategyUpdate, db: DbSession) -> Strategy:
    strategy = await _get_strategy(strategy_id, db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(strategy, key, value)
    await db.flush()
    await db.refresh(strategy)
    return strategy


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete strategy",
    dependencies=WRITE,
)
async def delete_strategy(strategy_id: int, db: DbSession) -> None:
    await db.delete(await _get_strategy(strategy_id, db))


# ── Backtests ─────────────────────────────────────────────────────


@router.post(
    "/{strategy_id}/backtest",
    response_model=BacktestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run a backtest (async; progress streams on the `backtests` WS channel)",
    responses={429: {"description": "Too many backtests running or queued"}},
    dependencies=WRITE,
)
async def run_backtest(strategy_id: int, request: BacktestRequest, db: DbSession) -> BacktestResult:
    strategy = await _get_strategy(strategy_id, db)
    try:
        spec = StrategySpec.model_validate(strategy.config)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid strategy config: {exc}"
        ) from exc
    symbol = (request.symbol or settings.default_symbol).upper()
    if symbol not in settings.SYMBOL_ALLOWLIST:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown symbol {symbol}")
    if not market_service.backtests.has_capacity():
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many backtests running or queued; try again when one finishes",
        )
    row = BacktestResult(
        strategy_id=strategy.id,
        symbol=symbol,
        status="pending",  # → running once a slot frees up
        data_source="pending",
        initial_capital=request.initial_capital,
        final_capital=request.initial_capital,
        commission_bps=request.commission_bps,
        slippage_bps=request.slippage_bps,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    await db.commit()
    market_service.backtests.submit(int(row.id), symbol, spec, request.model_dump())
    return row


@router.get(
    "/{strategy_id}/backtests", response_model=BacktestPage, summary="List backtests, newest first"
)
async def list_backtests(
    strategy_id: int,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    before: int | None = Query(None, ge=1, description="`next_before` of the previous page"),
) -> dict[str, Any]:
    await _get_strategy(strategy_id, db)
    q = (
        select(BacktestResult)
        .where(BacktestResult.strategy_id == strategy_id)
        .order_by(BacktestResult.id.desc())
        .limit(limit + 1)
    )
    if before is not None:
        q = q.where(BacktestResult.id < before)
    return page(list((await db.execute(q)).scalars().all()), limit)


@router.get(
    "/{strategy_id}/backtests/{backtest_id}",
    response_model=BacktestDetailResponse,
    summary="Backtest detail with trades and equity curve",
)
async def get_backtest(strategy_id: int, backtest_id: int, db: DbSession) -> BacktestResult:
    row = (
        await db.execute(
            select(BacktestResult).where(
                BacktestResult.id == backtest_id, BacktestResult.strategy_id == strategy_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backtest not found")
    return row
