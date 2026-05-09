"""
AlgoViz Backend — API Integration Tests
==========================================

Tests for REST API endpoints using httpx TestClient.
"""

import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Create async test client."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health(client):
    """Health endpoint returns correct structure."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "uptime_seconds" in data
    assert "market_connected" in data
    assert "ws_clients" in data
    assert "timestamp" in data


@pytest.mark.anyio
async def test_root(client):
    """Root endpoint returns API info."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "app" in data
    assert "docs" in data


@pytest.mark.anyio
async def test_analytics_insights(client):
    """Analytics insights returns a list."""
    response = await client.get("/api/v1/analytics/insights")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_analytics_prediction(client):
    """Analytics prediction returns prediction object."""
    response = await client.get("/api/v1/analytics/prediction")
    assert response.status_code == 200
    data = response.json()
    assert "direction" in data
    assert "confidence" in data


@pytest.mark.anyio
async def test_analytics_model_info(client):
    """Model info returns status."""
    response = await client.get("/api/v1/analytics/model-info")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.anyio
async def test_analytics_summary(client):
    """Summary returns combined data."""
    response = await client.get("/api/v1/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert "features" in data
    assert "insights" in data
    assert "prediction" in data
    assert "timestamp" in data


@pytest.mark.anyio
async def test_strategies_list(client):
    """Strategies list returns array."""
    response = await client.get("/api/v1/strategies/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_market_features(client):
    """Market features returns current features."""
    response = await client.get("/api/v1/market/features")
    assert response.status_code == 200
    data = response.json()
    assert "symbol" in data or "current_price" in data


@pytest.mark.anyio
async def test_request_id_header(client):
    """Middleware injects X-Request-ID header."""
    response = await client.get("/health")
    assert "x-request-id" in response.headers


@pytest.mark.anyio
async def test_response_time_header(client):
    """Middleware injects X-Response-Time header."""
    response = await client.get("/health")
    assert "x-response-time" in response.headers
    assert "ms" in response.headers["x-response-time"]
