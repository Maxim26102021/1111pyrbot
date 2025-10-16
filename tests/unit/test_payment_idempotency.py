from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import json
import pytest

from services.payments.app import dao


class FakeResult:
    def __init__(self, mapping=None):
        self._mapping = mapping

    def mappings(self):
        return self

    def first(self):
        return self._mapping


class FakeSession:
    def __init__(self, responses, executed):
        self._responses = responses
        self.executed = executed

    async def execute(self, query, params=None):
        self.executed.append((str(query), params))
        if self._responses:
            return self._responses.pop(0)
        return FakeResult()


def make_scope_sequence(responses_sequence, executed):
    iterator = iter(responses_sequence)

    @asynccontextmanager
    async def _scope(_url):
        responses = list(next(iterator))
        session = FakeSession(responses, executed)
        yield session

    return _scope


def test_insert_payment_idempotent(monkeypatch: pytest.MonkeyPatch):
    row = {"id": 1, "ext_id": "abc", "provider": "tbank"}
    responses_sequence = [[FakeResult(row.copy())], [FakeResult(row.copy())]]
    executed = []
    monkeypatch.setattr(dao, "session_scope", make_scope_sequence(responses_sequence, executed))

    payload = {"foo": "bar"}
    first = asyncio.run(dao.insert_payment_idempotent(
        "dummy",
        user_id=1,
        provider="tbank",
        ext_id="abc",
        amount=100,
        currency="RUB",
        status="payment.succeeded",
        payload=payload,
    ))

    second = asyncio.run(dao.insert_payment_idempotent(
        "dummy",
        user_id=1,
        provider="tbank",
        ext_id="abc",
        amount=100,
        currency="RUB",
        status="payment.succeeded",
        payload=payload,
    ))

    assert first["id"] == second["id"]
    assert len(executed) == 2
    assert json.loads(executed[0][1]["payload"]) == payload
