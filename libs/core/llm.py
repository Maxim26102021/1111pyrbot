from __future__ import annotations

import hashlib
import os
from typing import Any

from openai import AsyncOpenAI


class LLMClient:
    """Thin wrapper around OpenAI Responses API."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        max_output_tokens: int = 512,
        temperature: float = 0.2,
    ) -> None:
        self._mode = os.getenv("LLM_MODE", "").lower()
        self._client = None if self._mode == "mock" else AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature

    async def summarize(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> tuple[str, dict[str, int]]:
        if self._mode == "mock":
            return _mock_response(prompt)

        response = await self._client.responses.create(
            model=self._model,
            input=prompt,
            temperature=temperature if temperature is not None else self._temperature,
            max_output_tokens=max_output_tokens if max_output_tokens is not None else self._max_output_tokens,
        )

        text = getattr(response, "output_text", None) or ""
        usage = _extract_usage(response)
        return text.strip(), usage


def _extract_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    prompt_tokens = getattr(usage, "input_tokens", 0)
    completion_tokens = getattr(usage, "output_tokens", 0)
    total_tokens = getattr(usage, "total_tokens", prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }


def _mock_response(prompt: str) -> tuple[str, dict[str, int]]:
    seed = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    items = []
    for idx in range(3):
        chunk = seed[idx * 6 : (idx + 1) * 6]
        items.append(f"• Mock summary item {idx + 1} ({chunk})")
    text = "⚡ Mock Digest\n" + "\n".join(items)
    usage = {
        "prompt_tokens": len(prompt.split()),
        "completion_tokens": 42,
        "total_tokens": len(prompt.split()) + 42,
    }
    return text, usage
