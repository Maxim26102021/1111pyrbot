from __future__ import annotations

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("BOT_ENV_FILE"),
        case_sensitive=False,
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    redis_url: str = Field(..., alias="REDIS_URL")
    database_url: str = Field(..., alias="DATABASE_URL")
    celery_broker_url: Optional[str] = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: Optional[str] = Field(default=None, alias="CELERY_RESULT_BACKEND")
    queue_bot: str = Field(default="bot", alias="QUEUE_BOT")
    queue_summarize_priority: str = Field(default="summarize_priority", alias="QUEUE_SUMMARIZE_PRIORITY")
    preview_sample_limit: int = Field(default=8, alias="PREVIEW_SAMPLE_LIMIT")
    telegram_parse_mode: str = Field(default="HTML", alias="TELEGRAM_PARSE_MODE")
    telegram_max_message: int = Field(default=3900, alias="TELEGRAM_MAX_MESSAGE")
    telegram_sleep_on_flood: str = Field(default="auto", alias="TELEGRAM_SLEEP_ON_FLOOD")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    compliance_mode: bool = Field(default=False, alias="COMPLIANCE_MODE")

    @property
    def broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def backend(self) -> str:
        return self.celery_result_backend or self.redis_url


def load_settings() -> BotSettings:
    return BotSettings()
