from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, status

from libs.core.logging import json_log

from .config import load_settings
from .dao import activate_subscription, get_user_by_ids, insert_payment_idempotent
from .models import TBankWebhook
from .security import verify_hmac

settings = load_settings()
logger = logging.getLogger(__name__)
SERVICE = "payments"

PAYMENTS_METRICS = {
    "webhooks_total": 0,
    "invalid_signature": 0,
    "unknown_user": 0,
    "succeeded": 0,
}

logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")

app = FastAPI(title="Payments Service", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/webhook/tbank")
async def webhook_tbank(request: Request, x_signature: Optional[str] = Header(default=None)) -> dict[str, object]:
    PAYMENTS_METRICS["webhooks_total"] += 1
    raw_body = await request.body()
    signature = x_signature

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    if not signature:
        signature = data.get("signature")

    if not signature or not verify_hmac(raw_body, signature, settings.webhook_secret):
        PAYMENTS_METRICS["invalid_signature"] += 1
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    payload = TBankWebhook.model_validate(data)

    user = await get_user_by_ids(
        settings.database_url,
        user_id=payload.user_id,
        tg_user_id=payload.tg_user_id,
    )

    if not user:
        PAYMENTS_METRICS["unknown_user"] += 1
        json_log(logger, "warning", "unknown_user", service=SERVICE, payload=data)
        return {"ok": True, "status": "unknown_user"}

    payment = await insert_payment_idempotent(
        settings.database_url,
        user_id=user["id"],
        provider=settings.provider,
        ext_id=payload.ext_id,
        amount=payload.amount,
        currency=payload.currency,
        status=payload.event,
        payload=data,
    )

    if payload.event == "payment.succeeded":
        PAYMENTS_METRICS["succeeded"] += 1
        await activate_subscription(
            settings.database_url,
            user_id=user["id"],
            plan=settings.default_plan,
            days=settings.subscription_duration_days,
        )

    json_log(
        logger,
        "info",
        "webhook_processed",
        service=SERVICE,
        user_id=user["id"],
        ext_id=payload.ext_id,
        status=payload.event,
    )
    return {"ok": True, "ext_id": payload.ext_id, "status": payload.event}


@app.get("/metrics")
async def metrics() -> dict[str, int]:
    return PAYMENTS_METRICS
