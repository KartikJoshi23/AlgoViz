"""
AlgoViz Backend — Strategy API Routes
========================================

CRUD endpoints for trading strategies and backtesting.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from database import get_db
from models.models import Strategy, BacktestResult, User
from schemas.schemas import (
    StrategyCreate, StrategyUpdate, StrategyResponse,
    BacktestRequest, BacktestResponse,
)

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
        await db.flush()  # flush, don't commit — let the session manager commit
        await db.refresh(user)
    return user


# ── CRUD ──────────────────────────────────────────────────────────

@router.get("/debug")
async def debug_strategies(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to test DB access."""
    import traceback
    try:
        # Test raw query
        result = await db.execute(select(User).limit(1))
        users = result.scalars().all()
        return {"status": "ok", "user_count": len(users), "users": [u.username for u in users]}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}

@router.get("/", response_model=List[StrategyResponse])
async def list_strategies(db: AsyncSession = Depends(get_db)):
    """List all strategies for the default user."""
    import traceback
    import logging
    logger = logging.getLogger("algoviz.strategies")
    try:
        user = await _get_or_create_default_user(db)
        result = await db.execute(
            select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.created_at.desc())
        )
        return result.scalars().all()
    except Exception as e:
        logger.error(f"list_strategies error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(data: StrategyCreate, db: AsyncSession = Depends(get_db)):
    """Create a new strategy."""
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
    return strategy


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific strategy."""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.patch("/{strategy_id}", response_model=StrategyResponse)
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
    return strategy


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a strategy."""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await db.delete(strategy)


# ── Backtesting ───────────────────────────────────────────────────

@router.post("/{strategy_id}/backtest", response_model=BacktestResponse)
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

    # TODO: Integrate enhanced backtester from Phase 3
    # For now, create a placeholder result
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
    return backtest


@router.get("/{strategy_id}/backtests", response_model=List[BacktestResponse])
async def list_backtests(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """List backtest results for a strategy."""
    result = await db.execute(
        select(BacktestResult)
        .where(BacktestResult.strategy_id == strategy_id)
        .order_by(BacktestResult.created_at.desc())
    )
    return result.scalars().all()
