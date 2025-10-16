from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx
from openai import APIStatusError, APITimeoutError, RateLimitError as OpenAIRateLimitError

from libs.core.llm import LLMClient
from libs.core.util import hash_text

from .celery_app import celery_app, settings
from .dao import (
    fetch_post,
    find_post_by_text_hash,
    find_summary_by_post,
    upsert_summary,
)

logger = logging.getLogger(__name__)

TECHNICAL_SUMMARY = "Короткая заметка, без суммаризации."


class RateLimitError(Exception):
    """Raised when LLM responds with rate limiting or throttling."""


llm_client = LLMClient(
    api_key=settings.openai_api_key,
    model=settings.llm_model,
    max_output_tokens=settings.llm_max_tokens,
    temperature=settings.llm_temperature,
)


async def summarize_post_logic(post_id: int, *, priority: bool = False, retries: int = 0) -> None:
    post = await fetch_post(settings.database_url, post_id)
    if not post:
        logger.warning("Post not found", extra={"post_id": post_id})
        return

    existing_summary = await find_summary_by_post(settings.database_url, post_id)
    if existing_summary:
        logger.info("Summary already exists", extra={"post_id": post_id})
        return

    raw_text = (post.get("raw_text") or "").strip()
    text_hash_value = post.get("text_hash") or hash_text(raw_text) if raw_text else ""

    if not raw_text or len(raw_text) < settings.min_text_len:
        await upsert_summary(
            settings.database_url,
            post_id=post_id,
            summary_text=TECHNICAL_SUMMARY,
            model="technical",
            tokens_in=None,
            tokens_out=None,
            cost=None,
        )
        logger.info(
            "Stored technical summary due to short text",
            extra={"post_id": post_id, "length": len(raw_text)},
        )
        return

    if text_hash_value:
        duplicate_post_id = await find_post_by_text_hash(
            settings.database_url,
            text_hash_value,
            exclude_post_id=post_id,
        )
        if duplicate_post_id:
            duplicate_summary = await find_summary_by_post(settings.database_url, duplicate_post_id)
            if duplicate_summary:
                await upsert_summary(
                    settings.database_url,
                    post_id=post_id,
                    summary_text=duplicate_summary["summary_text"],
                    model=duplicate_summary["model"],
                    tokens_in=duplicate_summary.get("tokens_in"),
                    tokens_out=duplicate_summary.get("tokens_out"),
                    cost=duplicate_summary.get("cost"),
                )
                logger.info(
                    "Reused cached summary",
                    extra={"post_id": post_id, "source_post_id": duplicate_post_id},
                )
                return

    trimmed = raw_text[: settings.max_text_len]

    prompt = build_prompt(post, trimmed)

    start_time = time.perf_counter()
    try:
        summary_text, usage = await asyncio.wait_for(
            llm_client.summarize(prompt),
            timeout=settings.summarize_timeout_seconds,
        )
    except (OpenAIRateLimitError, APITimeoutError) as exc:
        raise RateLimitError(str(exc)) from exc
    except APIStatusError as exc:
        if getattr(exc, "status_code", None) == 429:
            raise RateLimitError(str(exc)) from exc
        raise
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            raise RateLimitError(str(exc)) from exc
        raise
    except httpx.TimeoutException as exc:
        raise RateLimitError(str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise RateLimitError(str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.exception("HTTP error while summarizing", extra={"post_id": post_id})
        raise
    finally:
        latency_ms = (time.perf_counter() - start_time) * 1000

    summary_text = (summary_text or "").strip()
    if not summary_text:
        summary_text = TECHNICAL_SUMMARY

    tokens_in = usage.get("prompt_tokens") if usage else None
    tokens_out = usage.get("completion_tokens") if usage else None
    cost = None

    await upsert_summary(
        settings.database_url,
        post_id=post_id,
        summary_text=summary_text,
        model=settings.llm_model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
    )

    logger.info(
        "Summary stored",
        extra={
            "post_id": post_id,
            "model": settings.llm_model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "retries": retries,
        },
    )


def build_prompt(post: Dict[str, Any], text: str) -> str:
    channel_id = post.get("channel_id")
    published_at = post.get("published_at")
    return (
        "system: Ты — лаконичный редактор новостей. Делай краткий дайджест: 3–5 пунктов,"
        " по делу, без лишних мнений. Язык — как у исходного текста.\n"
        f"Канал: {channel_id}\n"
        f"Дата: {published_at}\n"
        f"Текст:\n{text}"
    )


@celery_app.task(
    name="summarize_post",
    bind=True,
    autoretry_for=(RateLimitError,),
    retry_kwargs={"max_retries": 6},
    retry_backoff=True,
    retry_jitter=True,
)
def summarize_post(self, post_id: int, priority: bool = False) -> None:
    asyncio.run(summarize_post_logic(post_id, priority=priority, retries=self.request.retries))
