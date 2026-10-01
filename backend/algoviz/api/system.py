"""System endpoints — WS schema anchor for type generation, runtime metrics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from algoviz.core.looplag import loop_lag
from algoviz.core.time import utcnow
from algoviz.market.service import market_service
from algoviz.schemas.rest import SystemMetricsResponse
from algoviz.schemas.ws import WSSchema
from algoviz.ws.hub import ws_manager

router = APIRouter(tags=["System"])


@router.get(
    "/ws/schema",
    response_model=WSSchema,
    summary="WebSocket message schemas (OpenAPI anchor; responds 204)",
    description=(
        "Exists so the server→client and client→server WebSocket message unions are part of "
        "the OpenAPI document (and therefore the generated TypeScript types). Always 204."
    ),
    responses={204: {"description": "No content — see components.schemas.WSSchema"}},
)
async def ws_schema() -> Response:
    return Response(status_code=204)


@router.get(
    "/system/metrics",
    response_model=SystemMetricsResponse,
    summary="Runtime metrics for the Settings page",
)
async def system_metrics() -> dict[str, Any]:
    return {
        **system_stats(),
        "ml": {s: e.ml.model_info() for s, e in market_service.engines.items() if e.ml is not None},
        "timestamp": utcnow().isoformat(),
    }


def system_stats() -> dict[str, Any]:
    """Engine, WebSocket and event-loop stats (also what `/metrics` exports)."""
    return {"market": market_service.stats(), "ws": ws_manager.stats(), "loop": loop_lag.stats()}
