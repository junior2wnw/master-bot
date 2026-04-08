"""Tests for MAX webhook runtime helpers and endpoint."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.max_webhook as max_webhook_api
import app.max_bot.app as max_runtime


def test_resolve_max_webhook_url_uses_webapp_origin():
    settings = SimpleNamespace(
        max_webhook_url="",
        max_webhook_path="/api/max/webhook",
        webapp_url="https://4-2.xn--p1ai/app",
    )

    assert max_runtime.resolve_max_webhook_url(settings) == "https://4-2.xn--p1ai/api/max/webhook"


def test_get_max_delivery_mode_prefers_webhook_in_production():
    settings = SimpleNamespace(
        max_delivery_mode="auto",
        max_webhook_url="",
        max_webhook_path="/api/max/webhook",
        webapp_url="https://4-2.xn--p1ai/app",
        is_dev=False,
    )

    assert max_runtime.get_max_delivery_mode(settings) == "webhook"


def test_get_max_delivery_mode_prefers_polling_in_dev_without_explicit_override():
    settings = SimpleNamespace(
        max_delivery_mode="auto",
        max_webhook_url="",
        max_webhook_path="/api/max/webhook",
        webapp_url="https://localhost:8000/app",
        is_dev=True,
    )

    assert max_runtime.get_max_delivery_mode(settings) == "polling"


def test_max_webhook_endpoint_requires_secret(monkeypatch):
    processed: list[dict] = []

    async def fake_process(payload):
        processed.append(payload)

    monkeypatch.setattr(
        max_webhook_api,
        "get_settings",
        lambda: SimpleNamespace(
            max_bot_token="token",
            max_webhook_secret="secret-123",
            max_webhook_path="/api/max/webhook",
            max_delivery_mode="webhook",
        ),
    )
    monkeypatch.setattr(max_webhook_api, "process_max_webhook_payload", fake_process)
    monkeypatch.setattr(max_webhook_api, "get_max_delivery_mode", lambda settings: "webhook")

    app = FastAPI()
    app.include_router(max_webhook_api.router)
    client = TestClient(app)

    response = client.post("/api/max/webhook", json={"update_type": "message_created"})
    assert response.status_code == 401
    assert processed == []


def test_max_webhook_endpoint_accepts_valid_secret(monkeypatch):
    processed: list[dict] = []

    async def fake_process(payload):
        processed.append(payload)

    monkeypatch.setattr(
        max_webhook_api,
        "get_settings",
        lambda: SimpleNamespace(
            max_bot_token="token",
            max_webhook_secret="secret-123",
            max_webhook_path="/api/max/webhook",
            max_delivery_mode="webhook",
        ),
    )
    monkeypatch.setattr(max_webhook_api, "process_max_webhook_payload", fake_process)
    monkeypatch.setattr(max_webhook_api, "get_max_delivery_mode", lambda settings: "webhook")

    app = FastAPI()
    app.include_router(max_webhook_api.router)
    client = TestClient(app)

    payload = {"update_type": "message_created", "message": {"body": {"text": "/start"}}}
    response = client.post(
        "/api/max/webhook",
        json=payload,
        headers={"X-Max-Bot-Api-Secret": "secret-123"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert processed == [payload]

