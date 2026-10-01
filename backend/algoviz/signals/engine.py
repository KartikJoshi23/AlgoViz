"""
Signal engine
=============

Evaluates the rule set against the feature context on every bar close and
emits **transitions** (activated / deactivated) rather than a full list every
tick. Keeps the active set, per-rule cooldowns, and a bounded history so a
client can populate its feed on reload.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from algoviz.signals.rules import DEFAULT_RULES, SignalRule

HISTORY = 200


@dataclass(slots=True)
class ActiveSignal:
    rule_id: str
    name: str
    priority: str
    message: str
    action: str
    impact: str
    tags: list[str]
    activated_at_ms: int
    values: dict[str, Any] = field(default_factory=dict)

    def payload(self, now_ms: int) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "priority": self.priority,
            "message": self.message,
            "action": self.action,
            "impact": self.impact,
            "tags": list(self.tags),
            "activated_at_ms": self.activated_at_ms,
            "seconds_active": round(max(now_ms - self.activated_at_ms, 0) / 1000, 1),
            "values": self.values,
        }


@dataclass(slots=True)
class Transition:
    ts_ms: int
    kind: str  # activated | deactivated
    signal: ActiveSignal
    duration_s: float | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "ts_ms": self.ts_ms,
            "kind": self.kind,
            "duration_s": self.duration_s,
            **self.signal.payload(self.ts_ms),
        }


class SignalEngine:
    def __init__(self, rules: tuple[SignalRule, ...] | list[SignalRule] = DEFAULT_RULES) -> None:
        self.rules: dict[str, SignalRule] = {r.id: r for r in rules}
        self._active: dict[str, ActiveSignal] = {}
        self._cooldown_until: dict[str, int] = {}
        self.history: deque[Transition] = deque(maxlen=HISTORY)
        self.evaluations = 0

    # ── Evaluation ────────────────────────────────────────────────

    def evaluate(self, ctx: dict[str, Any], now_ms: int) -> list[Transition]:
        """Evaluate every enabled rule; return the transitions that occurred."""
        self.evaluations += 1
        out: list[Transition] = []
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            active = self._active.get(rule.id)
            if active is None:
                if now_ms < self._cooldown_until.get(rule.id, 0):
                    continue
                if rule.enter.evaluate(ctx):
                    sig = ActiveSignal(
                        rule_id=rule.id,
                        name=rule.name,
                        priority=rule.priority,
                        message=rule.render(ctx),
                        action=rule.action,
                        impact=rule.impact,
                        tags=list(rule.tags),
                        activated_at_ms=now_ms,
                        values=self._values(rule, ctx),
                    )
                    self._active[rule.id] = sig
                    t = Transition(now_ms, "activated", sig)
                    self.history.append(t)
                    out.append(t)
            else:
                elapsed = (now_ms - active.activated_at_ms) / 1000.0
                local_ctx = {**ctx, "seconds_active": elapsed}
                if elapsed >= rule.min_duration_s and rule.exit.evaluate(local_ctx):
                    del self._active[rule.id]
                    self._cooldown_until[rule.id] = now_ms + int(rule.cooldown_s * 1000)
                    t = Transition(now_ms, "deactivated", active, duration_s=round(elapsed, 1))
                    self.history.append(t)
                    out.append(t)
                else:
                    # refresh the message with current values while active
                    active.message = rule.render(ctx)
                    active.values = self._values(rule, ctx)
        return out

    @staticmethod
    def _values(rule: SignalRule, ctx: dict[str, Any]) -> dict[str, Any]:
        return {f: ctx.get(f) for f in sorted(rule.fields()) if f in ctx}

    # ── Reads ─────────────────────────────────────────────────────

    def active(self, now_ms: int) -> list[dict[str, Any]]:
        order = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            (s.payload(now_ms) for s in self._active.values()),
            key=lambda p: (order.get(p["priority"], 9), -p["activated_at_ms"]),
        )

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return [t.payload() for t in list(self.history)[-limit:]][::-1]

    def rules_payload(self) -> list[dict[str, Any]]:
        return [
            {
                **r.model_dump(mode="json", by_alias=True),
                "enter_text": r.enter.describe(),
                "exit_text": r.exit.describe(),
                "active": r.id in self._active,
            }
            for r in self.rules.values()
        ]

    def reset(self) -> None:
        self._active.clear()
        self._cooldown_until.clear()
