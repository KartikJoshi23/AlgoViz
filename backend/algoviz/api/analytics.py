"""Analytics endpoints — prediction, model, drift, explainability, signals."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from algoviz.db import async_session, page
from algoviz.market.service import SymbolEngine, market_service
from algoviz.schemas.rest import (
    DriftResponse,
    ModelInfoResponse,
    ModelRegistryPage,
    ShapResponse,
    SignalRuleResponse,
    SignalsStateResponse,
)
from algoviz.schemas.ws import PredictionPayload, RegimePayload

router = APIRouter(prefix="/analytics", tags=["Analytics"])

SymbolQuery = Query(None, description="Symbol; defaults to the primary symbol", max_length=20)


def _engine(symbol: str | None) -> SymbolEngine:
    e = market_service.get(symbol)
    if e is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "market engine not running")
    if e.ml is None or e.signals is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "intelligence tier disabled")
    return e


@router.get(
    "/prediction", response_model=PredictionPayload | None, summary="Latest calibrated prediction"
)
async def get_prediction(symbol: str | None = SymbolQuery) -> dict[str, Any] | None:
    e = _engine(symbol)
    assert e.ml is not None
    return e.ml.last_payload()


@router.get(
    "/model-info",
    response_model=ModelInfoResponse,
    summary="Model status, walk-forward metrics, drift",
)
async def get_model_info(symbol: str | None = SymbolQuery) -> dict[str, Any]:
    e = _engine(symbol)
    assert e.ml is not None
    return e.ml.model_info()


@router.get(
    "/model-registry",
    response_model=ModelRegistryPage,
    summary="Trained model versions, newest first",
)
async def get_model_registry(
    symbol: str | None = SymbolQuery,
    limit: int = Query(20, ge=1, le=100),
    before: int | None = Query(None, ge=1, description="`next_before` of the previous page"),
) -> dict[str, Any]:
    e = _engine(symbol)
    assert e.ml is not None
    rows = await e.ml.registry.history(async_session, limit=limit + 1, before=before)
    return page(rows, limit)


@router.get("/drift", response_model=DriftResponse, summary="Realised-outcome drift monitor")
async def get_drift(
    symbol: str | None = SymbolQuery, limit: int = Query(300, ge=10, le=2000)
) -> dict[str, Any]:
    e = _engine(symbol)
    assert e.ml is not None
    return {"symbol": e.symbol, "summary": e.ml.drift.summary(), "series": e.ml.drift.series(limit)}


@router.get(
    "/shap",
    response_model=ShapResponse | None,
    summary="SHAP contributions for the latest prediction",
)
async def get_shap(symbol: str | None = SymbolQuery) -> dict[str, Any] | None:
    e = _engine(symbol)
    assert e.ml is not None
    out = await e.ml.explain()  # computed on the inference thread, never on the loop
    return {"symbol": e.symbol, **out} if out else None


@router.get(
    "/regime", response_model=RegimePayload, summary="Current regime (alias of /market/regime)"
)
async def get_regime(symbol: str | None = SymbolQuery) -> dict[str, Any]:
    return _engine(symbol)._regime_payload()


@router.get(
    "/signals", response_model=SignalsStateResponse, summary="Active signals and recent transitions"
)
async def get_signals(
    symbol: str | None = SymbolQuery, limit: int = Query(50, ge=1, le=200)
) -> dict[str, Any]:
    e = _engine(symbol)
    assert e.signals is not None
    return {
        "symbol": e.symbol,
        "active": e.signals.active(e.now_ms()),
        "recent": e.signals.recent(limit),
    }


@router.get(
    "/signals/rules", response_model=list[SignalRuleResponse], summary="Signal rule definitions"
)
async def get_signal_rules(symbol: str | None = SymbolQuery) -> list[dict[str, Any]]:
    e = _engine(symbol)
    assert e.signals is not None
    return e.signals.rules_payload()
