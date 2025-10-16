from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TBankWebhook(BaseModel):
    event: Literal["payment.succeeded", "payment.failed", "payment.pending"]
    ext_id: str
    user_id: Optional[int] = None
    tg_user_id: Optional[int] = Field(default=None, alias="tg_user_id")
    amount: Decimal
    currency: str = "RUB"
    paid_at: Optional[datetime] = None
    signature: Optional[str] = None
