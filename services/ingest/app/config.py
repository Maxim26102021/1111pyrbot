from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("INGEST_ENV_FILE"),
        case_sensitive=False,
    )

    tg_api_id: int = Field(...)
    tg_api_hash: str = Field(...)
    sessions_dir: Path = Field(Path("/sessions"))
    channel_source: str = Field("env")
    channel_ids_raw: str = Field("")
    redis_url: str = Field(...)
    database_url: str = Field(...)
    celery_broker_url: str | None = Field(None)
    celery_result_backend: str | None = Field(None)
    queue_summarize: str = Field("summarize")
    log_level: str = Field("INFO")

    @field_validator("channel_source")
    @classmethod
    def validate_channel_source(cls, value: str) -> str:
        allowed = {"env", "db"}
        value_lower = value.lower()
        if value_lower not in allowed:
            raise ValueError(f"INGEST_CHANNEL_SOURCE must be one of {allowed}, got {value}")
        return value_lower

    @property
    def channel_ids(self) -> List[int]:
        items = []
        for raw in self.channel_ids_raw.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                items.append(int(raw))
            except ValueError:
                raise ValueError(f"Invalid channel id in INGEST_CHANNEL_IDS: {raw}") from None
        return items

    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


def load_settings() -> IngestSettings:
    return IngestSettings()
