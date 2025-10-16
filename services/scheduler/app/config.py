from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("SCHEDULER_ENV_FILE"),
        case_sensitive=False,
    )

    redis_url: str = Field(...)
    database_url: str = Field(...)
    celery_broker_url: Optional[str] = Field(default=None)
    celery_result_backend: Optional[str] = Field(default=None)
    queue_digest: str = Field(default="digest")
    queue_bot: str = Field(default="bot")
    digest_period_minutes: int = Field(default=30)
    digest_lookback_hours: int = Field(default=12)
    digest_jitter_seconds: int = Field(default=120)
    log_level: str = Field(default="INFO")

    @property
    def broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def period_timedelta(self) -> timedelta:
        return timedelta(minutes=self.digest_period_minutes)

    @property
    def lookback_timedelta(self) -> timedelta:
        return timedelta(hours=self.digest_lookback_hours)


def load_settings() -> SchedulerSettings:
    return SchedulerSettings()
