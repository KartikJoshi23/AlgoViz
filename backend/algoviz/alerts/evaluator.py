"""
Alert evaluator
===============

Runs on every bar close (1 Hz) against the enabled `AlertRule` rows for the
symbol. Rules are cached in memory and reloaded when the CRUD router calls
`invalidate()`. A rule that fires writes an `AlertHistory` row, publishes an
`alert` frame over the hub (never dropped), and — if configured — posts to
Discord. Per-rule cooldowns are enforced in memory and persisted through
`last_fired_at`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algoviz.alerts import templates
from algoviz.alerts.notify import DiscordNotifier
from algoviz.core.conditions import Cond
from algoviz.core.time import utcnow
from algoviz.models import AlertHistory, AlertRule
from algoviz.ws.hub import Hub

logger = logging.getLogger("algoviz.alerts")

_OP_TO_COND = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "==", "in": "in"}


class AlertEvaluator:
    def __init__(
        self,
        sf: async_sessionmaker[AsyncSession],
        hub: Hub,
        notifier: DiscordNotifier | None = None,
    ) -> None:
        self._sf = sf
        self._hub = hub
        self._notifier = notifier
        self._rules: dict[str, list[tuple[AlertRule, Cond]]] = {}  # symbol → rules
        self._last_fired_ms: dict[int, int] = {}
        self._loaded = False
        self._lock = asyncio.Lock()
        self._loading: asyncio.Task[None] | None = None
        self._deliveries: set[asyncio.Task[bool]] = (
            set()
        )  # in-flight Discord posts (kept referenced)
        self.fired = 0
        self.evaluations = 0

    # ── Rule cache ────────────────────────────────────────────────

    def invalidate(self) -> None:
        self._loaded = False

    async def refresh(self) -> None:
        async with self._lock:
            async with self._sf() as session:
                rows: Sequence[AlertRule] = (
                    (await session.execute(select(AlertRule).where(AlertRule.is_enabled.is_(True))))
                    .scalars()
                    .all()
                )
            cache: dict[str, list[tuple[AlertRule, Cond]]] = {}
            for r in rows:
                try:
                    cond = Cond.model_validate(
                        {
                            "f": r.condition_field,
                            "op": _OP_TO_COND.get(r.comparison, r.comparison),
                            "v": r.threshold,
                        }
                    )
                except Exception:
                    logger.warning("alert rule %d has an invalid condition; skipped", r.id)
                    continue
                cache.setdefault(r.symbol.upper(), []).append((r, cond))
                if r.last_fired_at is not None:
                    self._last_fired_ms.setdefault(r.id, int(r.last_fired_at.timestamp() * 1000))
            self._rules = cache
            self._loaded = True

    def rule_count(self, symbol: str | None = None) -> int:
        if symbol:
            return len(self._rules.get(symbol.upper(), []))
        return sum(len(v) for v in self._rules.values())

    # ── Evaluation ────────────────────────────────────────────────

    async def evaluate(self, symbol: str, ctx: dict[str, Any], now_ms: int) -> list[dict[str, Any]]:
        if not self._loaded:
            await self.refresh()
        self.evaluations += 1
        fired: list[dict[str, Any]] = []
        for rule, cond in self._rules.get(symbol.upper(), []):
            if not cond.evaluate(ctx):
                continue
            last = self._last_fired_ms.get(rule.id)
            if last is not None and now_ms - last < rule.cooldown_seconds * 1000:
                continue
            self._last_fired_ms[rule.id] = now_ms
            try:
                payload = await self._fire(rule, cond, ctx, now_ms)
            except Exception:  # one broken rule must not silence the ones after it
                logger.exception("alert rule %d failed to fire", rule.id)
                continue
            if payload is not None:
                fired.append(payload)
        return fired

    async def _fire(
        self, rule: AlertRule, cond: Cond, ctx: dict[str, Any], now_ms: int
    ) -> dict[str, Any] | None:
        value = ctx.get(rule.condition_field)
        message = self._render(rule, value)
        triggered_at = utcnow()
        try:
            async with self._sf() as session:
                row = AlertHistory(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    symbol=rule.symbol,
                    priority=rule.priority,
                    message=message,
                    field=rule.condition_field,
                    value=float(value) if isinstance(value, int | float) else None,
                    threshold=rule.threshold,
                    triggered_at=triggered_at,
                )
                session.add(row)
                db_rule = await session.get(AlertRule, rule.id)
                if db_rule is not None:
                    db_rule.last_fired_at = triggered_at
                await session.commit()
                await session.refresh(row)
                alert_id = int(row.id)
        except Exception:
            logger.exception("alert persistence failed for rule %d", rule.id)
            return None

        payload = {
            "id": alert_id,
            "rule_id": rule.id,
            "rule_name": rule.name,
            "symbol": rule.symbol,
            "priority": rule.priority,
            "message": message,
            "field": rule.condition_field,
            "value": float(value) if isinstance(value, int | float) else None,
            "threshold": rule.threshold,
            "triggered_at": triggered_at.isoformat(),
        }
        self.fired += 1
        self._hub.publish("alerts", rule.symbol, payload)
        if rule.notify_discord and self._notifier is not None and self._notifier.enabled:
            task = asyncio.get_running_loop().create_task(self._notifier.send(payload))
            self._deliveries.add(task)
            task.add_done_callback(self._deliveries.discard)
        return payload

    @staticmethod
    def _render(rule: AlertRule, value: Any) -> str:
        v = f"{value:.4g}" if isinstance(value, int | float) else str(value)
        default = (
            f"{rule.name}: {rule.condition_field} = {v} ({rule.comparison} {rule.threshold:g})"
        )
        return templates.render(
            rule.message_template,
            default,
            value=value,
            threshold=rule.threshold,
            field=rule.condition_field,
            symbol=rule.symbol,
        )

    def stats(self) -> dict[str, Any]:
        return {
            "rules_cached": self.rule_count(),
            "evaluations": self.evaluations,
            "fired": self.fired,
            "discord": {
                "enabled": bool(self._notifier and self._notifier.enabled),
                "sent": self._notifier.sent if self._notifier else 0,
                "failed": self._notifier.failed if self._notifier else 0,
            },
        }
