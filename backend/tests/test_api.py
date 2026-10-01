"""API integration tests — system, market, analytics, strategies, alerts, auth."""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from algoviz.core.middleware import Message, Receive, Scope, Send

# ── System ────────────────────────────────────────────────────────


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert data["version"] == "3.0.0"
    assert data["environment"] == "test"
    assert data["symbols"] == ["BTCUSDT"]
    assert data["data_source"] == "synthetic"
    assert data["market_connected"] is True
    assert isinstance(data["ws_clients"], int)


async def test_root(client: AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json()["api"] == "/api/v1"


async def test_observability_headers(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert len(r.headers["x-request-id"]) == 12
    assert r.headers["x-response-time"].endswith("ms")


async def test_openapi_exposes_all_routers(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    paths = spec["paths"]
    for p in (
        "/api/v1/market/features",
        "/api/v1/analytics/prediction",
        "/api/v1/strategies",
        "/api/v1/alerts/rules",
        "/api/v1/auth/login",
    ):
        assert p in paths, p


# ── Market ────────────────────────────────────────────────────────


async def test_market_features_shape(client: AsyncClient) -> None:
    data = (await client.get("/api/v1/market/features")).json()
    for key in (
        "symbol", "source", "warmed_up", "last_price", "mid", "microprice", "spread_bps",
        "imbalance_w", "ofi_5s", "velocity", "volatility_bps", "spread_z", "regime",
        "p_up", "p_down",
    ):  # fmt: skip
        assert key in data, key
    assert "current_price" not in data  # legacy keys are gone
    assert data["symbol"] == "BTCUSDT" and data["source"] == "synthetic"
    assert data["mid"] > 0 and data["spread_bps"] > 0


async def test_market_symbol_validation(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/market/features?symbol=DOGEUSDT")).status_code == 404
    assert (await client.get("/api/v1/market/features?symbol=btcusdt")).status_code == 200
    syms = (await client.get("/api/v1/market/symbols")).json()
    assert syms["active"] == ["BTCUSDT"] and "ETHUSDT" in syms["allowlist"]


async def test_market_trades(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/market/trades?limit=0")).status_code == 422
    trades = (await client.get("/api/v1/market/trades?limit=10")).json()
    assert 0 < len(trades) <= 10
    assert set(trades[0]) == {"ts_ms", "price", "qty", "side", "trade_id"}
    assert trades[0]["side"] in ("buy", "sell")


async def test_market_book(client: AsyncClient) -> None:
    data = (await client.get("/api/v1/market/book?depth=5")).json()
    assert len(data["bids"]) == 5 and len(data["asks"]) == 5
    assert data["bids"][0][0] < data["asks"][0][0]  # best bid below best ask
    assert data["bids"][0][0] > data["bids"][1][0]  # bids descend
    assert data["asks"][0][0] < data["asks"][1][0]  # asks ascend
    assert data["levels"] == 98 and data["update_id"] > 0  # 25 near + 24 far per side
    prof = data["profile"]
    assert prof["bins"] == 64 and len(prof["bids"]) == 64 and len(prof["asks"]) == 64
    assert prof["bids"] == sorted(prof["bids"])  # cumulative from mid outward
    assert (await client.get("/api/v1/market/book?depth=0")).status_code == 422


async def test_market_bars_ring_and_history(client: AsyncClient) -> None:
    ring = (await client.get("/api/v1/market/bars?limit=5")).json()
    assert ring["columns"][:5] == ["ts_ms", "open", "high", "low", "close"]
    assert 1 <= len(ring["rows"]) <= 5 and len(ring["rows"][0]) == len(ring["columns"])
    # history path (DB) — the writer flushes every 5 s, so this may be empty; must not error
    hist = await client.get("/api/v1/market/bars?start_ms=0&limit=10")
    assert hist.status_code == 200 and "rows" in hist.json()


async def test_market_regime_and_catalog(client: AsyncClient) -> None:
    reg = (await client.get("/api/v1/market/regime")).json()
    assert reg["label"] in ("calm", "normal", "elevated", "extreme")
    assert reg["trend"] in ("down", "flat", "up") and isinstance(reg["trend_t"], float)
    assert reg["source"] in ("fallback", "hmm")
    assert set(reg["probs"]) == {"calm", "normal", "elevated", "extreme"}
    cat = (await client.get("/api/v1/market/feature-catalog")).json()
    names = {c["name"] for c in cat}
    assert {"spread_z", "ofi_5s", "microprice", "regime", "trend", "p_up"} <= names
    regime = next(c for c in cat if c["name"] == "regime")
    assert regime["ops"] == ["eq", "in"] and regime["values"] == [
        "calm",
        "normal",
        "elevated",
        "extreme",
    ]
    trend = next(c for c in cat if c["name"] == "trend")
    assert trend["kind"] == "categorical" and trend["values"] == ["down", "flat", "up"]


async def test_market_stats_shape(client: AsyncClient) -> None:
    st = (await client.get("/api/v1/market/stats")).json()
    e = st["symbols"]["BTCUSDT"]
    assert e["book"]["state"] == "synced" and e["events"] > 0
    assert e["source"]["name"] == "synthetic"
    assert "writer" in st and "ws" in st


async def test_ws_schema_anchor_and_openapi_unions(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/ws/schema")).status_code == 204
    schemas = (await client.get("/openapi.json")).json()["components"]["schemas"]
    for name in (
        "WSSchema", "HelloMessage", "SnapshotMessage", "FeaturesMessage", "BookMessage",
        "SubscribeMessage", "PingMessage",
    ):  # fmt: skip
        assert name in schemas, name


async def test_system_metrics(client: AsyncClient) -> None:
    m = (await client.get("/api/v1/system/metrics")).json()
    assert {"market", "ws", "ml", "timestamp"} <= set(m)


# ── Analytics ─────────────────────────────────────────────────────


async def test_prediction_contract(client: AsyncClient) -> None:
    r = await client.get("/api/v1/analytics/prediction")
    assert r.status_code == 200
    data = r.json()
    # None until 60 bars exist; otherwise a typed payload (warming_up before training)
    if data is not None:
        assert data["status"] in ("warming_up", "ready", "error")
        assert data["signal"] in ("long", "short", "flat")
        assert data["horizon_s"] == 5 and data["samples_required"] > 0
        assert data["drift"]["status"] == "no_data"


async def test_model_info_contract(client: AsyncClient) -> None:
    from algoviz.ml.features import N_FEATURES

    data = (await client.get("/api/v1/analytics/model-info")).json()
    assert data["status"] in ("warming_up", "training", "ready")
    assert data["model_version"] == 0 and data["samples_required"] == 300
    assert len(data["feature_names"]) == N_FEATURES
    assert data["metrics"] == {"oos": {}, "folds": [], "reliability": None}
    assert data["feature_importance"] == {} and data["feature_importance_std"] == {}
    assert data["drift"]["status"] == "no_data"
    assert (await client.get("/api/v1/analytics/model-registry")).json() == {
        "items": [],
        "next_before": None,
    }
    assert (await client.get("/api/v1/analytics/shap")).json() is None
    drift = (await client.get("/api/v1/analytics/drift")).json()
    assert (
        drift["symbol"] == "BTCUSDT"
        and drift["summary"]["status"] == "no_data"
        and drift["series"] == []
    )


async def test_signals_endpoints(client: AsyncClient) -> None:
    st = (await client.get("/api/v1/analytics/signals")).json()
    assert (
        st["symbol"] == "BTCUSDT"
        and isinstance(st["active"], list)
        and isinstance(st["recent"], list)
    )
    rules = (await client.get("/api/v1/analytics/signals/rules")).json()
    assert len(rules) >= 14
    r0 = next(r for r in rules if r["id"] == "spread_widening")
    assert (
        r0["enter_text"] == "spread_z > 2.0"
        and r0["priority"] == "high"
        and isinstance(r0["active"], bool)
    )
    assert (await client.get("/api/v1/analytics/regime")).json()["label"] in (
        "calm",
        "normal",
        "elevated",
        "extreme",
    )


# ── Strategies & backtests ────────────────────────────────────────


async def test_strategy_crud_and_async_backtest(client: AsyncClient) -> None:
    import asyncio

    assert (await client.get("/api/v1/strategies")).json() == []
    examples = (await client.get("/api/v1/strategies/examples")).json()
    assert {e["id"] for e in examples} >= {"ofi_momentum", "queue_imbalance_scalp", "model_signal"}
    spec = next(e["config"] for e in examples if e["id"] == "queue_imbalance_scalp")

    # invalid config is rejected by the strategy-spec validator
    r = await client.post("/api/v1/strategies", json={"name": "bad", "config": {"side": "long"}})
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/strategies", json={"name": "x", "strategy_type": "bogus", "config": spec}
    )
    assert r.status_code == 422

    r = await client.post(
        "/api/v1/strategies",
        json={
            "name": "Scalp",
            "description": "test",
            "strategy_type": "rule_based",
            "config": spec,
        },
    )
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["name"] == "Scalp" and s["config"]["entry_long"]["f"] == "imbalance_l1"
    sid = s["id"]

    r = await client.patch(f"/api/v1/strategies/{sid}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False

    # backtest: 202 immediately, completes in the background on synthetic history
    r = await client.post(
        f"/api/v1/strategies/{sid}/backtest", json={"initial_capital": 5000, "lookback_minutes": 5}
    )
    assert r.status_code == 202, r.text
    bt = r.json()
    assert bt["status"] == "pending" and bt["initial_capital"] == 5000  # running once it has a slot
    for _ in range(300):
        detail = (await client.get(f"/api/v1/strategies/{sid}/backtests/{bt['id']}")).json()
        if detail["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.1)
    assert detail["status"] == "completed", detail
    assert detail["data_source"] == "synthetic"
    assert detail["final_capital"] > 0 and isinstance(detail["total_trades"], int)
    assert len(detail["equity_curve"]) > 100 and isinstance(detail["trades"], list)
    listing = (await client.get(f"/api/v1/strategies/{sid}/backtests")).json()["items"]
    assert listing[0]["id"] == bt["id"] and "equity_curve" not in listing[0]

    assert (
        await client.post(f"/api/v1/strategies/{sid}/backtest", json={"symbol": "DOGEUSDT"})
    ).status_code == 422
    assert (await client.delete(f"/api/v1/strategies/{sid}")).status_code == 204
    assert (await client.get(f"/api/v1/strategies/{sid}")).status_code == 404


# ── Alerts ────────────────────────────────────────────────────────


async def test_alert_rule_crud_and_firing(client: AsyncClient) -> None:
    import asyncio

    r = await client.post(
        "/api/v1/alerts/rules",
        json={"name": "Always", "condition_field": "mid", "comparison": "gt", "threshold": 0,
              "priority": "high", "cooldown_seconds": 300},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["symbol"] == "BTCUSDT" and rule["priority"] == "high" and rule["is_enabled"]

    # unknown field / invalid operator are rejected against the catalog
    for bad in (
        {"name": "b", "condition_field": "nope", "comparison": "gt", "threshold": 1},
        {"name": "b", "condition_field": "regime", "comparison": "gt", "threshold": 1},
        {"name": "b", "condition_field": "x", "comparison": "between", "threshold": 1},
    ):
        assert (await client.post("/api/v1/alerts/rules", json=bad)).status_code == 422

    # the evaluator runs on bar close (1 Hz): the rule must fire exactly once (cooldown 300 s)
    fired = []
    for _ in range(40):
        fired = (await client.get("/api/v1/alerts/history")).json()["items"]
        if fired:
            break
        await asyncio.sleep(0.1)
    assert len(fired) == 1, fired
    a = fired[0]
    assert (
        a["rule_name"] == "Always"
        and a["field"] == "mid"
        and a["value"] > 0
        and not a["acknowledged"]
    )
    await asyncio.sleep(1.2)
    assert len((await client.get("/api/v1/alerts/history")).json()["items"]) == 1  # cooldown
    assert (await client.get("/api/v1/alerts/rules")).json()[0]["last_fired_at"] is not None

    assert (await client.post(f"/api/v1/alerts/history/{a['id']}/acknowledge")).json()["count"] == 1
    unacked = (await client.get("/api/v1/alerts/history?unacknowledged_only=true")).json()
    assert unacked == {"items": [], "next_before": None}

    r = await client.patch(
        f"/api/v1/alerts/rules/{rule['id']}", json={"threshold": 7.5, "is_enabled": False}
    )
    assert r.status_code == 200 and r.json()["threshold"] == 7.5 and r.json()["is_enabled"] is False
    assert (await client.delete(f"/api/v1/alerts/rules/{rule['id']}")).status_code == 204


# ── Auth ──────────────────────────────────────────────────────────


async def test_auth_flow(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register", json={"username": "kartik", "password": "s3cret-pass"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["username"] == "kartik"

    assert (
        await client.post(
            "/api/v1/auth/register", json={"username": "kartik", "password": "s3cret-pass"}
        )
    ).status_code == 409
    assert (
        await client.post("/api/v1/auth/login", json={"username": "kartik", "password": "wrong"})
    ).status_code == 401

    r = await client.post(
        "/api/v1/auth/login", json={"username": "kartik", "password": "s3cret-pass"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]

    assert (await client.get("/api/v1/auth/me")).status_code == 401
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["username"] == "kartik"
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
    ).status_code == 401


# ── Stage G: commit ordering, health probes, capacity, template validation ──


async def test_writes_are_committed_before_the_response_is_sent(app: FastAPI) -> None:
    """A client that re-reads right after a 2xx must see its own write (read-after-write)."""
    from sqlalchemy import select

    from algoviz.db import async_session
    from algoviz.models import Strategy

    seen_at_response: list[bool] = []
    name = f"raw-{uuid.uuid4().hex[:8]}"

    async def probe(scope: Scope, receive: Receive, send: Send) -> None:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                async with async_session() as s:  # another connection, like the next request
                    row = (
                        await s.execute(select(Strategy.id).where(Strategy.name == name))
                    ).scalar_one_or_none()
                seen_at_response.append(row is not None)
            await send(message)

        await app(scope, receive, send_wrapper)

    spec = {"side": "long", "entry_long": {"f": "ofi_z", "op": ">", "v": 2}, "max_hold_s": 10}
    async with AsyncClient(transport=ASGITransport(app=probe), base_url="http://test") as c:
        r = await c.post("/api/v1/strategies", json={"name": name, "config": spec})
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        seen_at_response.clear()
        assert (await c.delete(f"/api/v1/strategies/{sid}")).status_code == 204
    # at the moment the 204 went out, the row was already gone for other connections
    assert seen_at_response == [False]


async def test_liveness_and_readiness_probes(client: AsyncClient) -> None:
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    r = await client.get("/health/ready")
    body = r.json()
    assert r.status_code == (200 if body["ready"] else 503)
    assert {"database", "market:BTCUSDT", "event_loop"} <= set(body["checks"])
    assert body["checks"]["database"] is True
    health = (await client.get("/health")).json()
    assert "loop_lag_p99_ms" in health
    loop = (await client.get("/api/v1/system/metrics")).json()["loop"]
    assert loop["samples"] > 0 and loop["p99_ms"] >= 0


async def test_backtests_beyond_capacity_are_refused(client: AsyncClient) -> None:
    from algoviz.market.service import market_service

    spec = {"side": "long", "entry_long": {"f": "ofi_z", "op": ">", "v": 2}, "max_hold_s": 10}
    sid = (await client.post("/api/v1/strategies", json={"name": "cap", "config": spec})).json()[
        "id"
    ]
    runner = market_service.backtests
    limit = runner.max_queued
    runner.max_queued = 0
    try:
        r = await client.post(f"/api/v1/strategies/{sid}/backtest", json={})
        assert r.status_code == 429, r.text
        listing = (await client.get(f"/api/v1/strategies/{sid}/backtests")).json()
        assert listing["items"] == []  # no orphan row
    finally:
        runner.max_queued = limit
    r = await client.post(
        f"/api/v1/strategies/{sid}/backtest", json={"lookback_minutes": 60 * 24 + 1}
    )
    assert r.status_code == 422  # lookback capped at one day of 1 s bars
    assert (await client.delete(f"/api/v1/strategies/{sid}")).status_code == 204


async def test_alert_templates_are_validated_on_create_and_update(client: AsyncClient) -> None:
    base = {"name": "tpl", "condition_field": "spread_z", "comparison": "gt", "threshold": 3}
    bad = await client.post(
        "/api/v1/alerts/rules", json={**base, "message_template": "{value.__class__}"}
    )
    assert bad.status_code == 422 and "placeholder" in bad.text
    ok = await client.post(
        "/api/v1/alerts/rules", json={**base, "message_template": "{symbol}: {value:+.2f}σ"}
    )
    assert ok.status_code == 201, ok.text
    rid = ok.json()["id"]
    r = await client.patch(
        f"/api/v1/alerts/rules/{rid}", json={"message_template": "{value:>9999}"}
    )
    assert r.status_code == 422
    assert (await client.delete(f"/api/v1/alerts/rules/{rid}")).status_code == 204
