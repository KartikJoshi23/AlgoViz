"""Market data endpoints — features, book, trades, bars, feature catalog, stats."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from algoviz.config import settings
from algoviz.core.time import utcnow
from algoviz.db import async_session
from algoviz.market.bars import BAR_COLUMNS
from algoviz.market.catalog import catalog_payload
from algoviz.market.persistence import load_bars
from algoviz.market.service import SymbolEngine, market_service
from algoviz.schemas.rest import FeatureCatalogEntry, MarketStatsResponse, SymbolsResponse
from algoviz.schemas.ws import BarRows, BookPayload, FeaturesPayload, RegimePayload, TradePayload

router = APIRouter(prefix="/market", tags=["Market Data"])

SymbolQuery = Query(None, description="Symbol; defaults to the primary symbol", max_length=20)


def _engine(symbol: str | None) -> SymbolEngine:
    engine = market_service.get(symbol)
    if engine is None:
        if symbol and symbol.upper() not in settings.SYMBOLS:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown symbol {symbol.upper()}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "market engine not running")
    return engine


@router.get("/symbols", response_model=SymbolsResponse, summary="Active symbols and allowlist")
async def get_symbols() -> dict[str, Any]:
    return {
        "active": settings.SYMBOLS,
        "default": settings.default_symbol,
        "allowlist": settings.SYMBOL_ALLOWLIST,
        "source": settings.DATA_SOURCE,
    }


@router.get("/features", response_model=FeaturesPayload, summary="Current streaming features")
async def get_features(symbol: str | None = SymbolQuery) -> dict[str, Any]:
    e = _engine(symbol)
    return e.features.snapshot(e.now_ms()).to_dict()


@router.get("/book", response_model=BookPayload | None, summary="L2 order book (top N)")
async def get_book(
    symbol: str | None = SymbolQuery, depth: int = Query(50, ge=1, le=500)
) -> dict[str, Any] | None:
    return _engine(symbol).book_payload(depth)


@router.get("/trades", response_model=list[TradePayload], summary="Recent trades")
async def get_trades(
    symbol: str | None = SymbolQuery, limit: int = Query(50, ge=1, le=200)
) -> list[dict[str, Any]]:
    e = _engine(symbol)
    return [e.trade_payload(t) for t in list(e.trade_ring)[-limit:]]


@router.get("/bars", response_model=BarRows, summary="1-second bars (in-memory ring or history)")
async def get_bars(
    symbol: str | None = SymbolQuery,
    start_ms: int | None = Query(None, ge=0),
    end_ms: int | None = Query(None, ge=0),
    limit: int = Query(600, ge=1, le=7200),
) -> dict[str, Any]:
    e = _engine(symbol)
    if start_ms is None and end_ms is None:
        rows = [b.compact() for b in list(e.bar_ring)[-limit:]]
    else:
        bars = await load_bars(
            async_session,
            e.symbol,
            source=e.source.name,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=limit,
        )
        rows = [b.compact() for b in bars]
    return {"columns": list(BAR_COLUMNS), "rows": rows}


@router.get("/regime", response_model=RegimePayload, summary="Current regime state")
async def get_regime(symbol: str | None = SymbolQuery) -> dict[str, Any]:
    return _engine(symbol)._regime_payload()


@router.get(
    "/feature-catalog",
    response_model=list[FeatureCatalogEntry],
    summary="Feature registry (names, units, allowed operators)",
)
async def get_feature_catalog() -> list[dict[str, Any]]:
    return catalog_payload()


@router.get("/stats", response_model=MarketStatsResponse, summary="Engine statistics (all symbols)")
async def get_stats() -> dict[str, Any]:
    return {**market_service.stats(), "timestamp": utcnow().isoformat()}
