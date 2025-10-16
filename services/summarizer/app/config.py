from __future__ import annotations

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SummarizerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("SUMMARIZER_ENV_FILE"),
        case_sensitive=False,
    )

    redis_url: str = Field(...)
    database_url: str = Field(...)
    celery_broker_url: Optional[str] = Field(default=None)
    celery_result_backend: Optional[str] = Field(default=None)
    queue_summarize: str = Field(default="summarize")
    queue_summarize_priority: str = Field(default="summarize_priority")

    llm_model: str = Field(default="gpt-4o-mini")
    llm_max_tokens: int = Field(default=512)
    llm_temperature: float = Field(default=0.2)
    summarize_timeout_seconds: int = Field(default=45)
    min_text_len: int = Field(default=200)
    max_text_len: int = Field(default=8000)

    log_level: str = Field(default="INFO")
    openai_api_key: str = Field(...)

    @property
    def broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def backend(self) -> str:
        return self.celery_result_backend or self.redis_url


def load_settings() -> SummarizerSettings:
    return SummarizerSettings()
