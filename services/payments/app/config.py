from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PaymentsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("PAYMENTS_ENV_FILE"),
        case_sensitive=False,
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    webhook_secret: str = Field(..., alias="PAYMENTS_WEBHOOK_SECRET")
    provider: str = Field(default="tbank", alias="PAYMENTS_PROVIDER")
    default_plan: str = Field(default="pro", alias="DEFAULT_SUBSCRIPTION_PLAN")
    subscription_duration_days: int = Field(default=30, alias="SUBSCRIPTION_DURATION_DAYS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


def load_settings() -> PaymentsSettings:
    return PaymentsSettings()
