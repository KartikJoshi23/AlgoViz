"""
Notification channels
=====================

Discord webhook delivery (fire-and-forget with a short timeout). Failures are
logged and counted, never raised into the evaluator.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("algoviz.alerts.notify")

_PRIORITY_COLOUR = {
    "critical": 0xFF1F4B,
    "high": 0xFF4D6D,
    "medium": 0xFFB020,
    "low": 0x19D3C5,
    "info": 0x3B6CFF,
}


class DiscordNotifier:
    def __init__(self, webhook_url: str | None, *, timeout_s: float = 5.0) -> None:
        self.url = webhook_url
        self._http = httpx.AsyncClient(timeout=timeout_s)
        self.sent = 0
        self.failed = 0

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    async def send(self, alert: dict[str, Any]) -> bool:
        if not self.url:
            return False
        embed = {
            "title": f"{alert.get('priority', 'medium').upper()} · {alert.get('rule_name', 'alert')}",
            "description": alert.get("message", ""),
            "color": _PRIORITY_COLOUR.get(str(alert.get("priority")), 0x8B5CF6),
            "fields": [
                {"name": "Symbol", "value": str(alert.get("symbol", "")), "inline": True},
                {"name": "Field", "value": str(alert.get("field", "")), "inline": True},
                {"name": "Value", "value": f"{alert.get('value')}", "inline": True},
            ],
            "footer": {"text": f"AlgoViz · {alert.get('triggered_at', '')}"},
        }
        try:
            r = await self._http.post(self.url, json={"embeds": [embed]})
            r.raise_for_status()
            self.sent += 1
            return True
        except Exception as exc:
            self.failed += 1
            logger.warning("discord notify failed: %s", exc)
            return False

    async def aclose(self) -> None:
        await self._http.aclose()
