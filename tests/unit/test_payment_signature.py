from __future__ import annotations

import importlib
import json
import os
from hashlib import sha256
hmac = __import__("hmac")

import pytest
from fastapi.testclient import TestClient


def load_api(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("PAYMENTS_WEBHOOK_SECRET", "secret")
    module = importlib.import_module("services.payments.app.api")
    importlib.reload(module)
    return module


def make_signature(secret: str, payload: dict) -> str:
    body = json.dumps(payload).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()


def test_valid_signature(monkeypatch: pytest.MonkeyPatch):
    api = load_api(monkeypatch)

    async def fake_get_user(*args, **kwargs):
        return {"id": 1}

    async def fake_insert(*args, **kwargs):
        return {"id": 10}

    async def fake_activate(*args, **kwargs):
        return None

    monkeypatch.setattr(api, "get_user_by_ids", fake_get_user)
    monkeypatch.setattr(api, "insert_payment_idempotent", fake_insert)
    monkeypatch.setattr(api, "activate_subscription", fake_activate)

    client = TestClient(api.app)
    payload = {
        "event": "payment.succeeded",
        "ext_id": "abc",
        "user_id": 1,
        "amount": 100,
        "currency": "RUB",
    }
    signature = make_signature(api.settings.webhook_secret, payload)
    response = client.post(
        "/webhook/tbank",
        headers={"X-Signature": signature},
        json=payload,
    )
    assert response.status_code == 200


def test_invalid_signature(monkeypatch: pytest.MonkeyPatch):
    api = load_api(monkeypatch)
    client = TestClient(api.app)
    payload = {"event": "payment.succeeded", "ext_id": "abc", "user_id": 1, "amount": 100}
    response = client.post(
        "/webhook/tbank",
        headers={"X-Signature": "deadbeef"},
        json=payload,
    )
    assert response.status_code == 403
