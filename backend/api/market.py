"""
AlgoViz Backend — Market API Routes
=====================================

REST endpoints for market data, features, charts, and insights.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from services.market_data import market_service

router = APIRouter(prefix="/market", tags=["Market Data"])


@router.get("/features")
async def get_features():
    """Get current calculated market features."""
    return market_service.get_features().to_dict()


@router.get("/trades")
async def get_trades(limit: int = Query(50, ge=1, le=500)):
    """Get recent trades."""
    return market_service.get_trades(limit=limit)


@router.get("/orderbook")
async def get_order_book():
    """Get current order book snapshot."""
    return market_service.get_order_book()


@router.get("/charts/price")
async def get_price_chart(window: int = Query(120, ge=10, le=3600)):
    """Get price & VWAP chart data."""
    return market_service.get_price_chart_data(window_seconds=window)


@router.get("/charts/spread")
async def get_spread_chart():
    """Get spread heatmap data."""
    return market_service.get_spread_chart_data()


@router.get("/charts/volatility")
async def get_volatility_chart():
    """Get volatility chart data."""
    return market_service.get_volatility_chart_data()


@router.get("/stats")
async def get_stats():
    """Get market data service statistics."""
    return market_service.get_stats()
