"""
AlgoViz Backend — Alerts API Routes
=====================================

CRUD endpoints for alert rules, alert history, and alert management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional, List
from datetime import datetime

from database import get_db
from models.models import AlertRule, AlertHistory, User
from schemas.schemas import (
    AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse,
    AlertHistoryResponse,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


# ── Default user helper ──────────────────────────────────────────

async def _get_default_user(db: AsyncSession) -> User:
    from api.strategies import _get_or_create_default_user
    return await _get_or_create_default_user(db)


# ── Alert Rules CRUD ─────────────────────────────────────────────

@router.get("/rules", response_model=List[AlertRuleResponse])
async def list_rules(db: AsyncSession = Depends(get_db)):
    """List all alert rules."""
    user = await _get_default_user(db)
    result = await db.execute(
        select(AlertRule)
        .where(AlertRule.user_id == user.id)
        .order_by(AlertRule.created_at.desc())
    )
    return result.scalars().all()


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(data: AlertRuleCreate, db: AsyncSession = Depends(get_db)):
    """Create a new alert rule."""
    user = await _get_default_user(db)
    rule = AlertRule(
        user_id=user.id,
        name=data.name,
        alert_type=data.alert_type,
        condition_field=data.condition_field,
        comparison=data.comparison,
        threshold=data.threshold,
        priority=data.priority,
        message_template=data.message_template,
        cooldown_seconds=data.cooldown_seconds,
        notify_discord=data.notify_discord,
        notify_email=data.notify_email,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_rule(
    rule_id: int,
    data: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an alert rule."""
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an alert rule."""
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    await db.delete(rule)


# ── Alert History ─────────────────────────────────────────────────

@router.get("/history", response_model=List[AlertHistoryResponse])
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
    return result.scalars().all()


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
