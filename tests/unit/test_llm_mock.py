from __future__ import annotations

import asyncio
import os

import pytest

from libs.core.llm import LLMClient


def test_llm_mock_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    client = LLMClient(api_key="fake", model="mock-model")
    text, usage = asyncio.run(client.summarize("Test prompt about AI news"))
    assert text.startswith("⚡ Mock Digest")
    assert "Mock summary item" in text
    assert usage["completion_tokens"] == 42
