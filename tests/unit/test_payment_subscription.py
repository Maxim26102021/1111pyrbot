from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

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
        self._responses = list(responses)
        self.executed = executed

    async def execute(self, query, params=None):
        self.executed.append((str(query), params))
        if self._responses:
            return self._responses.pop(0)
        return FakeResult()


def make_scope(responses, executed):
    @asynccontextmanager
    async def _scope(_url):
        session = FakeSession(responses, executed)
        yield session

    return _scope


def test_activate_subscription_creates_when_missing(monkeypatch: pytest.MonkeyPatch):
    executed = []
    responses = [FakeResult(None)]
    monkeypatch.setattr(dao, "session_scope", make_scope(responses, executed))

    asyncio.run(dao.activate_subscription("dummy", user_id=1, plan="pro", days=30))

    assert len(executed) == 2
    _, insert_params = executed[1]
    assert insert_params["plan"] == "pro"
    paid_until = insert_params["paid_until"]
    assert isinstance(paid_until, datetime)
    assert paid_until > datetime.now(timezone.utc)


def test_activate_subscription_extends_existing(monkeypatch: pytest.MonkeyPatch):
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=10)
    executed = []
    responses = [FakeResult({"id": 5, "paid_until": future})]
    monkeypatch.setattr(dao, "session_scope", make_scope(responses, executed))

    asyncio.run(dao.activate_subscription("dummy", user_id=1, plan="pro", days=30))

    assert len(executed) == 2
    _, update_params = executed[1]
    expected = future + timedelta(days=30)
    assert abs((update_params["paid_until"] - expected).total_seconds()) < 1
