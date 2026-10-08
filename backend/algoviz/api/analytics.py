"""Analytics endpoints — prediction, model, drift, edge study, explainability, signals."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ValidationError

from algoviz.config import settings
from algoviz.db import async_session, page
from algoviz.market.persistence import bar_coverage, newest_bar_ms
from algoviz.market.service import SymbolEngine, market_service
from algoviz.ml.study import FREEZE_MS, MIN_DAYS
from algoviz.schemas.rest import (
    DriftResponse,
    EdgeStudyReport,
    EdgeStudyResponse,
    ModelInfoResponse,
    ModelRegistryPage,
    ShapResponse,
    SignalRuleResponse,
    SignalsStateResponse,
)
from algoviz.schemas.ws import PredictionPayload, RegimePayload

logger = logging.getLogger("algoviz.api")

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


COVERAGE_TTL_S = (
    30.0  # the counts: the panels poll each minute, and counting weeks of bars isn't free
)
_coverage: dict[str, tuple[float, tuple[int, int, int | None, int | None]]] = {}


@router.get(
    "/edge-study",
    response_model=EdgeStudyResponse,
    summary="The latest edge study on this host, and how far data collection has come",
)
async def get_edge_study(symbol: str | None = SymbolQuery) -> dict[str, Any]:
    e = market_service.get(symbol)
    if e is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "market engine not running")
    return {"study": _latest_study(), "collection": await _collection(e.symbol)}


def _latest_study() -> dict[str, Any] | None:
    try:
        return EdgeStudyReport.model_validate_json(
            settings.EDGE_STUDY_FILE.read_bytes()
        ).model_dump()
    except FileNotFoundError:
        return None
    except (OSError, ValidationError) as exc:  # a report this server can't read counts as none
        logger.warning("edge study %s unreadable: %s", settings.EDGE_STUDY_FILE, exc)
        return None


async def _collection(symbol: str) -> dict[str, Any]:
    now = time.monotonic()
    cached = _coverage.get(symbol)
    if cached is None or now - cached[0] >= COVERAGE_TTL_S:
        counts = await bar_coverage(async_session, symbol, settings.DATA_SOURCE, FREEZE_MS)
        cached = _coverage[symbol] = (now, counts)
    n, n_since, oldest, _ = cached[1]
    newest = await newest_bar_ms(
        async_session, symbol, settings.DATA_SOURCE
    )  # fresh, unlike the counts
    return {
        "symbol": symbol,
        "source": settings.DATA_SOURCE,
        "bars": n,
        "days": round(n / 86_400, 4),
        "bars_since_freeze": n_since,
        "days_since_freeze": round(n_since / 86_400, 4),
        "days_required": MIN_DAYS,
        "freeze_ms": FREEZE_MS,
        "oldest_ms": oldest,
        "newest_ms": newest,
        "newest_age_s": None if newest is None else round(time.time() - newest / 1000, 1),
        "retention_days": settings.SNAPSHOT_RETENTION_DAYS,
    }


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
