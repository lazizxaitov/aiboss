"""Tests for health, root and core data layer behavior."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AI Business OS Core",
        "version": "0.1.0",
        "environment": "development",
    }


def test_root_endpoint() -> None:
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "AI Business OS Core"
    assert payload["version"] == "0.1.0"
    assert payload["docs"] == "/docs"
