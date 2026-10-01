"""Alert rule CRUD and alert history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from algoviz.config import settings
from algoviz.core.auth import require_writer
from algoviz.core.time import utcnow
from algoviz.core.users import get_or_create_default_user
from algoviz.db import DbSession, page
from algoviz.market.service import market_service
from algoviz.models import AlertHistory, AlertRule
from algoviz.schemas.rest import (
    AcknowledgeResponse,
    AlertHistoryPage,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])

WRITE = [Depends(require_writer)]  # mutations: see core/auth.py


async def _get_rule(rule_id: int, db: AsyncSession) -> AlertRule:
    rule = (await db.execute(select(AlertRule).where(AlertRule.id == rule_id))).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert rule not found")
    return rule


# ── Rules ─────────────────────────────────────────────────────────


@router.get("/rules", response_model=list[AlertRuleResponse], summary="List alert rules")
async def list_rules(db: DbSession) -> list[AlertRule]:
    user = await get_or_create_default_user(db)
    rows = await db.execute(
        select(AlertRule).where(AlertRule.user_id == user.id).order_by(AlertRule.created_at.desc())
    )
    return list(rows.scalars().all())


@router.post(
    "/rules",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create alert rule",
    dependencies=WRITE,
)
async def create_rule(data: AlertRuleCreate, db: DbSession) -> AlertRule:
    user = await get_or_create_default_user(db)
    payload = data.model_dump()
    payload["symbol"] = (payload.get("symbol") or settings.default_symbol).upper()
    rule = AlertRule(user_id=user.id, **payload)
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    market_service.alert_evaluator.invalidate()
    return rule


@router.patch(
    "/rules/{rule_id}",
    response_model=AlertRuleResponse,
    summary="Update alert rule",
    dependencies=WRITE,
)
async def update_rule(rule_id: int, data: AlertRuleUpdate, db: DbSession) -> AlertRule:
    rule = await _get_rule(rule_id, db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    await db.flush()
    await db.refresh(rule)
    market_service.alert_evaluator.invalidate()
    return rule


@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete alert rule",
    dependencies=WRITE,
)
async def delete_rule(rule_id: int, db: DbSession) -> None:
    await db.delete(await _get_rule(rule_id, db))
    market_service.alert_evaluator.invalidate()


# ── History ───────────────────────────────────────────────────────


@router.get("/history", response_model=AlertHistoryPage, summary="Alert history, newest first")
async def get_history(
    db: DbSession,
    limit: int = Query(50, ge=1, le=500),
    before: int | None = Query(None, ge=1, description="`next_before` of the previous page"),
    priority: str | None = Query(None),
    unacknowledged_only: bool = Query(False),
) -> dict[str, Any]:
    q = select(AlertHistory).order_by(AlertHistory.id.desc()).limit(limit + 1)
    if before is not None:
        q = q.where(AlertHistory.id < before)
    if priority:
        q = q.where(AlertHistory.priority == priority.lower())
    if unacknowledged_only:
        q = q.where(AlertHistory.acknowledged.is_(False))
    return page(list((await db.execute(q)).scalars().all()), limit)


@router.post(
    "/history/acknowledge-all",
    response_model=AcknowledgeResponse,
    summary="Acknowledge all alerts",
    dependencies=WRITE,
)
async def acknowledge_all(db: DbSession) -> AcknowledgeResponse:
    result: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
        update(AlertHistory)
        .where(AlertHistory.acknowledged.is_(False))
        .values(acknowledged=True, acknowledged_at=utcnow())
    )
    return AcknowledgeResponse(count=result.rowcount or 0)


@router.post(
    "/history/{alert_id}/acknowledge",
    response_model=AcknowledgeResponse,
    summary="Acknowledge alert",
    dependencies=WRITE,
)
async def acknowledge_alert(alert_id: int, db: DbSession) -> AcknowledgeResponse:
    alert = (
        await db.execute(select(AlertHistory).where(AlertHistory.id == alert_id))
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    if not alert.acknowledged:
        alert.acknowledged = True
        alert.acknowledged_at = utcnow()
    return AcknowledgeResponse(count=1)
