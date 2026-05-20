"""
AlgoViz Backend — Alerts API Routes
=====================================

CRUD endpoints for alert rules, alert history, and alert management.
"""

import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional, List
from datetime import datetime

from database import get_db
from models.models import AlertRule, AlertHistory

logger = logging.getLogger("algoviz.alerts")

router = APIRouter(prefix="/alerts", tags=["Alerts"])


# ── Default user helper ──────────────────────────────────────────

async def _get_default_user(db: AsyncSession):
    from api.strategies import _get_or_create_default_user
    return await _get_or_create_default_user(db)


def _rule_to_dict(r: AlertRule) -> dict:
    """Convert AlertRule ORM to dict."""
    return {
        "id": r.id,
        "name": r.name,
        "alert_type": r.alert_type,
        "condition_field": r.condition_field,
        "comparison": r.comparison,
        "threshold": r.threshold,
        "priority": r.priority,
        "is_enabled": r.is_enabled,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _history_to_dict(a: AlertHistory) -> dict:
    """Convert AlertHistory ORM to dict."""
    return {
        "id": a.id,
        "rule_id": a.rule_id,
        "priority": a.priority,
        "message": a.message,
        "value": a.value,
        "threshold": a.threshold,
        "acknowledged": a.acknowledged,
        "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
    }


# ── Alert Rules CRUD ─────────────────────────────────────────────

@router.get("/rules")
async def list_rules(db: AsyncSession = Depends(get_db)):
    """List all alert rules."""
    try:
        user = await _get_default_user(db)
        result = await db.execute(
            select(AlertRule)
            .where(AlertRule.user_id == user.id)
            .order_by(AlertRule.created_at.desc())
        )
        return [_rule_to_dict(r) for r in result.scalars().all()]
    except Exception as e:
        logger.error(f"list_rules error: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(data: dict, db: AsyncSession = Depends(get_db)):
    """Create a new alert rule."""
    try:
        user = await _get_default_user(db)
        rule = AlertRule(
            user_id=user.id,
            name=data.get("name", "Unnamed"),
            alert_type=data.get("alert_type", "custom"),
            condition_field=data.get("condition_field", "current_price"),
            comparison=data.get("comparison", "gt"),
            threshold=float(data.get("threshold", 0)),
            priority=data.get("priority", "medium"),
            message_template=data.get("message_template"),
            cooldown_seconds=int(data.get("cooldown_seconds", 30)),
            notify_discord=bool(data.get("notify_discord", False)),
            notify_email=bool(data.get("notify_email", False)),
        )
        db.add(rule)
        await db.flush()
        await db.refresh(rule)
        return _rule_to_dict(rule)
    except Exception as e:
        logger.error(f"create_rule error: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update an alert rule."""
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    allowed = {"name", "threshold", "priority", "is_enabled", "cooldown_seconds"}
    for key, value in data.items():
        if key in allowed:
            setattr(rule, key, value)
    await db.flush()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an alert rule."""
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    await db.delete(rule)


# ── Alert History ─────────────────────────────────────────────────

@router.get("/history")
async def get_history(
    limit: int = 50,
    priority: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get alert history with optional priority filter."""
    query = select(AlertHistory).order_by(desc(AlertHistory.triggered_at)).limit(limit)
    if priority:
        query = query.where(AlertHistory.priority == priority)
    result = await db.execute(query)
    return [_history_to_dict(a) for a in result.scalars().all()]


@router.post("/history/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Acknowledge a triggered alert."""
    result = await db.execute(select(AlertHistory).where(AlertHistory.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    return {"status": "acknowledged"}


@router.post("/history/acknowledge-all")
async def acknowledge_all(db: AsyncSession = Depends(get_db)):
    """Acknowledge all unacknowledged alerts."""
    result = await db.execute(
        select(AlertHistory).where(AlertHistory.acknowledged == False)
    )
    alerts = result.scalars().all()
    for a in alerts:
        a.acknowledged = True
        a.acknowledged_at = datetime.utcnow()
    return {"status": "acknowledged", "count": len(alerts)}
