from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from libs.core.pg import session_scope

from .config import load_settings
from .dao import activate_subscription, get_user_by_ids, insert_payment_idempotent
from .models import TBankWebhook
from .security import verify_hmac

settings = load_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title="Payments Service", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/webhook/tbank")
async def webhook_tbank(request: Request, x_signature: Optional[str] = Header(default=None)) -> dict[str, object]:
    raw_body = await request.body()
    signature = x_signature

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    if not signature:
        signature = data.get("signature")

    if not signature or not verify_hmac(raw_body, signature, settings.webhook_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    payload = TBankWebhook.model_validate(data)

    user = await get_user_by_ids(
        settings.database_url,
        user_id=payload.user_id,
        tg_user_id=payload.tg_user_id,
    )

    if not user:
        logger.warning("Webhook received for unknown user", extra={"payload": data})
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
        await activate_subscription(
            settings.database_url,
            user_id=user["id"],
            plan=settings.default_plan,
            days=settings.subscription_duration_days,
        )

    return {"ok": True, "ext_id": payload.ext_id, "status": payload.event}
