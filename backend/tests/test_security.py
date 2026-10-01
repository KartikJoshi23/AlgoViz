"""Stage M — who may change things, what errors look like, and how the server protects itself."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from algoviz.config import settings
from algoviz.core.logging import RepeatFilter
from algoviz.core.middleware import Message, RateLimitMiddleware, Receive, Scope, Send
from algoviz.main import create_app

PROBLEM = "application/problem+json"
TOKEN = "a" * 40


@pytest.fixture
def auth_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MUTATIONS_REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)


# ── Who may change things ─────────────────────────────────────────


@pytest.mark.usefixtures("auth_on")
async def test_mutations_need_the_admin_token_or_a_user_jwt(client: AsyncClient) -> None:
    body = {
        "name": "gated",
        "config": {
            "side": "long",
            "entry_long": {"f": "ofi_z", "op": ">", "v": 2},
            "stop_loss_bps": 10,
        },
    }
    r = await client.post("/api/v1/strategies", json=body)
    assert r.status_code == 401 and r.headers["content-type"] == PROBLEM
    assert r.headers["www-authenticate"] == "Bearer" and "admin token" in r.json()["detail"]
    bad = await client.post(
        "/api/v1/strategies", json=body, headers={"Authorization": "Bearer nope"}
    )
    assert bad.status_code == 401
    assert (await client.get("/api/v1/strategies")).status_code == 200  # reads stay public
    for path in ("/api/v1/alerts/history/acknowledge-all", "/api/v1/alerts/rules"):
        assert (await client.post(path, json={})).status_code == 401

    access = (await client.get("/api/v1/auth/access")).json()
    assert access == {"writes_require_auth": True, "can_write": False}
    auth = {"Authorization": f"Bearer {TOKEN}"}
    assert (await client.get("/api/v1/auth/access", headers=auth)).json()["can_write"] is True
    ok = await client.post(
        "/api/v1/strategies", json=body, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert ok.status_code == 201, ok.text
    sid = ok.json()["id"]

    # a signed-in user's JWT works as well
    name = "writer-user"
    assert (
        await client.post(
            "/api/v1/auth/register", json={"username": name, "password": "correct-horse"}
        )
    ).status_code == 201
    jwt = (
        await client.post(
            "/api/v1/auth/login", json={"username": name, "password": "correct-horse"}
        )
    ).json()["access_token"]
    r = await client.delete(f"/api/v1/strategies/{sid}", headers={"Authorization": f"Bearer {jwt}"})
    assert r.status_code == 204


async def test_registration_can_be_closed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)
    r = await client.post(
        "/api/v1/auth/register", json={"username": "late", "password": "correct-horse"}
    )
    assert r.status_code == 403 and r.json()["detail"] == "Registration is disabled on this server"


# ── Problem details ───────────────────────────────────────────────


async def test_errors_are_rfc9457_problems(client: AsyncClient) -> None:
    r = await client.get("/api/v1/strategies/999999")
    assert r.status_code == 404 and r.headers["content-type"] == PROBLEM
    p = r.json()
    assert p["type"] == "about:blank" and p["title"] == "Not Found" and p["status"] == 404
    assert p["detail"] == "Strategy not found" and p["instance"] == "/api/v1/strategies/999999"
    assert p["request_id"] == r.headers["x-request-id"]

    r = await client.post("/api/v1/alerts/rules", json={"name": "", "comparison": "sideways"})
    assert r.status_code == 422 and r.headers["content-type"] == PROBLEM
    p = r.json()
    fields = {e["loc"][-1] for e in p["errors"]}
    assert {"name", "comparison", "condition_field"} <= fields and p["detail"].endswith(
        "invalid fields"
    )


async def test_unhandled_errors_do_not_leak_details() -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret connection string")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/boom")
    assert r.status_code == 500 and r.headers["content-type"] == PROBLEM
    assert "secret" not in r.text and r.json()["title"] == "Internal Server Error"


async def test_openapi_documents_every_error_as_a_problem(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    assert "Problem" in spec["components"]["schemas"]
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    for path, item in spec["paths"].items():
        for op in item.values():
            for code, resp in op["responses"].items():
                if code == "default" or int(code) >= 400:
                    assert list(resp["content"]) == [PROBLEM], (path, code)


# ── Rate limits and the client address ───────────────────────────


async def _call(
    app: Any,
    method: str,
    path: str,
    client: str = "1.2.3.4",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    out: dict[str, Any] = {"body": b""}

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
            out["headers"] = {k.decode(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            out["body"] += message.get("body", b"")

    scope: Scope = {
        "type": "http", "method": method, "path": path, "headers": headers or [], "client": (client, 5000),
        "scheme": "http", "server": ("test", 80), "query_string": b"", "http_version": "1.1", "root_path": "",
    }  # fmt: skip
    await app(scope, receive, send)
    return out["status"], out["headers"], out["body"]


async def _ok(scope: Scope, receive: Receive, send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"x-client", scope["client"][0].encode())],
        }
    )
    await send({"type": "http.response.body", "body": b"ok"})


async def test_writes_and_backtests_have_their_own_stricter_limits() -> None:
    app = RateLimitMiddleware(
        _ok, requests_per_minute=100, writes_per_minute=3, backtests_per_minute=1
    )
    assert (await _call(app, "POST", "/api/v1/strategies/1/backtest"))[0] == 200
    status, headers, body = await _call(app, "POST", "/api/v1/strategies/1/backtest")
    assert status == 429 and headers["content-type"] == PROBLEM and int(headers["retry-after"]) >= 1
    assert b"backtest submissions" in body
    assert (await _call(app, "POST", "/api/v1/alerts/rules"))[0] == 200  # writes 2 of 3
    assert (await _call(app, "PATCH", "/api/v1/alerts/rules/1"))[0] == 200  # 3 of 3
    assert (await _call(app, "DELETE", "/api/v1/alerts/rules/1"))[0] == 429
    assert (await _call(app, "GET", "/api/v1/strategies"))[0] == 200  # reads keep their own budget
    assert (await _call(app, "POST", "/api/v1/alerts/rules", client="5.6.7.8"))[
        0
    ] == 200  # per client


async def test_forwarded_addresses_are_believed_only_from_trusted_proxies() -> None:
    app = ProxyHeadersMiddleware(
        RateLimitMiddleware(_ok, requests_per_minute=1), trusted_hosts=["10.0.0.0/8"]
    )
    xff = [(b"x-forwarded-for", b"203.0.113.9")]
    # a direct client can't pick its own rate-limit key by sending the header
    _, h, _ = await _call(app, "GET", "/x", client="198.51.100.7", headers=xff)
    assert h["x-client"] == "198.51.100.7"
    assert (
        await _call(
            app, "GET", "/x", client="198.51.100.7", headers=[(b"x-forwarded-for", b"1.1.1.1")]
        )
    )[0] == 429
    # through the trusted proxy, the forwarded client is the key
    _, h, _ = await _call(app, "GET", "/x", client="10.1.2.3", headers=xff)
    assert h["x-client"] == "203.0.113.9"


# ── WebSocket guards ──────────────────────────────────────────────


async def _handshake(app: Any, origin: str) -> list[Message]:
    """Drive one WebSocket handshake over raw ASGI; return what the server sent."""
    sent: list[Message] = []
    inbox: asyncio.Queue[Message] = asyncio.Queue()
    inbox.put_nowait({"type": "websocket.connect"})

    async def receive() -> Message:
        return await inbox.get()

    async def send(message: Message) -> None:
        sent.append(message)
        if message["type"] == "websocket.close":
            inbox.put_nowait({"type": "websocket.disconnect", "code": message.get("code", 1000)})

    scope: Scope = {
        "type": "websocket", "path": "/ws", "headers": [(b"origin", origin.encode())],
        "client": ("127.0.0.1", 5000), "scheme": "ws", "server": ("test", 80),
        "query_string": b"", "root_path": "", "subprotocols": [],
    }  # fmt: skip
    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    return sent


async def test_websocket_refuses_foreign_origins_and_a_full_house(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()  # no lifespan: the guards run before the hub is involved
    sent = await _handshake(app, "https://evil.example")
    assert [m["type"] for m in sent] == ["websocket.close"] and sent[0]["code"] == 1008
    monkeypatch.setattr(settings, "WS_MAX_CLIENTS", 0)
    sent = await _handshake(app, settings.CORS_ORIGINS[0])
    assert [m["type"] for m in sent] == ["websocket.accept", "websocket.close"]
    assert sent[1]["code"] == 1013


# ── Metrics, logs, shutdown ───────────────────────────────────────


async def test_metrics_endpoint_exports_the_engine(client: AsyncClient) -> None:
    await asyncio.sleep(1.2)  # a bar closes and events flow
    r = await client.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    text = r.text
    for name in (
        'algoviz_feed_events_total{symbol="BTCUSDT"}',
        'algoviz_event_loop_lag_ms{quantile="0.99"}',
        "algoviz_ws_clients",
        "algoviz_bars_written_total",
        "algoviz_db_errors_total",
        "algoviz_backtests_active",
    ):
        assert name in text, name
    assert (
        'algoviz_feed_latency_ms_count{symbol="BTCUSDT"}' in text
        or "algoviz_feed_latency_ms" in text
    )


def test_repeated_warnings_are_collapsed() -> None:
    f = RepeatFilter(window_s=60)

    def rec(msg: str, level: int = logging.WARNING) -> logging.LogRecord:
        return logging.LogRecord("algoviz.binance", level, __file__, 1, msg, None, None)

    assert f.filter(rec("stream closed: 1011"))
    assert not f.filter(rec("stream closed: 1011"))
    assert not f.filter(rec("stream closed: 1011"))
    assert f.filter(rec("snapshot fetch failed"))  # a different message passes
    assert f.filter(rec("stream closed: 1011", logging.INFO))  # info is never held back
    f._seen[("algoviz.binance", logging.WARNING, "stream closed: 1011")] = (
        0.0,
        2,
    )  # the window has passed
    r = rec("stream closed: 1011")
    assert f.filter(r) and "repeated 2×" in r.getMessage()


async def test_shutdown_marks_running_backtests_failed() -> None:
    from algoviz.market.service import market_service

    runner = market_service.backtests
    marked: list[tuple[int, str]] = []

    async def fail(result_id: int, error: str) -> None:
        marked.append((result_id, error))

    async def forever() -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await fail(4242, "the server shut down during this backtest")
            raise

    runner._jobs[4242] = asyncio.create_task(forever())
    await asyncio.sleep(0)
    await runner.stop()
    assert marked == [(4242, "the server shut down during this backtest")]
    runner._jobs.clear()


# ── Pagination ────────────────────────────────────────────────────


async def test_alert_history_pages_without_gaps_or_repeats(client: AsyncClient) -> None:
    from algoviz.core.time import utcnow
    from algoviz.db import async_session
    from algoviz.models import AlertHistory, AlertRule

    async with async_session() as s:
        rule = AlertRule(
            user_id=1,
            name="pager",
            symbol="BTCUSDT",
            condition_field="mid",
            comparison="gt",
            threshold=0,
        )
        s.add(rule)
        await s.flush()
        for i in range(7):
            s.add(
                AlertHistory(
                    rule_id=rule.id,
                    rule_name="pager",
                    priority="low",
                    message=f"m{i}",
                    field="mid",
                    triggered_at=utcnow(),
                )
            )
        await s.commit()
    seen: list[int] = []
    before: int | None = None
    while True:
        q = f"/api/v1/alerts/history?limit=3&priority=low{'' if before is None else f'&before={before}'}"
        page = (await client.get(q)).json()
        seen += [a["id"] for a in page["items"] if a["rule_name"] == "pager"]
        before = page["next_before"]
        if before is None:
            break
    assert len(seen) == 7 and seen == sorted(seen, reverse=True) and len(set(seen)) == 7
