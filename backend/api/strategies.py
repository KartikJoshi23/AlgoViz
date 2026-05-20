"""
AlgoViz Backend — Strategy API Routes
========================================

CRUD endpoints for trading strategies and backtesting.
"""

import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from database import get_db
from models.models import Strategy, BacktestResult, User
from schemas.schemas import (
    StrategyCreate, StrategyUpdate, StrategyResponse,
    BacktestRequest, BacktestResponse,
)

logger = logging.getLogger("algoviz.strategies")

router = APIRouter(prefix="/strategies", tags=["Strategies"])


# ── Default user helper (for single-user mode before auth) ────────

async def _get_or_create_default_user(db: AsyncSession) -> User:
    """Get or create a default user for single-user mode."""
    result = await db.execute(select(User).where(User.username == "default"))
    user = result.scalar_one_or_none()
    if not user:
        from core.auth import hash_password
        user = User(
            username="default",
            hashed_password=hash_password("algoviz"),
            is_admin=True,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
    return user


def _strategy_to_dict(s: Strategy) -> dict:
    """Convert a Strategy ORM model to a dict for JSON serialization."""
    return {
        "id": s.id,
        "user_id": s.user_id,
        "name": s.name,
        "description": s.description,
        "strategy_type": s.strategy_type,
        "config": s.config or {},
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _backtest_to_dict(b: BacktestResult) -> dict:
    """Convert a BacktestResult ORM model to a dict."""
    return {
        "id": b.id,
        "strategy_id": b.strategy_id,
        "total_pnl": b.total_pnl,
        "total_pnl_pct": b.total_pnl_pct,
        "total_trades": b.total_trades,
        "win_rate": b.win_rate,
        "max_drawdown_pct": b.max_drawdown_pct,
        "sharpe_ratio": b.sharpe_ratio,
        "profit_factor": b.profit_factor,
        "initial_capital": b.initial_capital,
        "final_capital": b.final_capital,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


# ── CRUD ──────────────────────────────────────────────────────────

@router.get("/")
async def list_strategies(db: AsyncSession = Depends(get_db)):
    """List all strategies for the default user."""
    try:
        user = await _get_or_create_default_user(db)
        result = await db.execute(
            select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.created_at.desc())
        )
        strategies = result.scalars().all()
        return [_strategy_to_dict(s) for s in strategies]
    except Exception as e:
        logger.error(f"list_strategies error: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_strategy(data: StrategyCreate, db: AsyncSession = Depends(get_db)):
    """Create a new strategy."""
    try:
        user = await _get_or_create_default_user(db)
        strategy = Strategy(
            user_id=user.id,
            name=data.name,
            description=data.description,
            strategy_type=data.strategy_type,
            config=data.config,
        )
        db.add(strategy)
        await db.flush()
        await db.refresh(strategy)
        return _strategy_to_dict(strategy)
    except Exception as e:
        logger.error(f"create_strategy error: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific strategy."""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return _strategy_to_dict(strategy)


@router.patch("/{strategy_id}")
async def update_strategy(
    strategy_id: int,
    data: StrategyUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a strategy."""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(strategy, key, value)
    await db.flush()
    await db.refresh(strategy)
    return _strategy_to_dict(strategy)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a strategy."""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await db.delete(strategy)


# ── Backtesting ───────────────────────────────────────────────────

@router.post("/{strategy_id}/backtest")
async def run_backtest(
    strategy_id: int,
    request: BacktestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run a backtest on a strategy."""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    backtest = BacktestResult(
        strategy_id=strategy.id,
        total_pnl=0.0,
        total_trades=0,
        win_rate=0.0,
        initial_capital=request.initial_capital,
        final_capital=request.initial_capital,
    )
    db.add(backtest)
    await db.flush()
    await db.refresh(backtest)
    return _backtest_to_dict(backtest)


@router.get("/{strategy_id}/backtests")
async def list_backtests(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """List backtest results for a strategy."""
    result = await db.execute(
        select(BacktestResult)
        .where(BacktestResult.strategy_id == strategy_id)
        .order_by(BacktestResult.created_at.desc())
    )
    return [_backtest_to_dict(b) for b in result.scalars().all()]
