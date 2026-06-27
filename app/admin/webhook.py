"""FastAPI webhook endpoint for ЮKassa payment notifications."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from sqlalchemy import select

from app.database.database import async_session
from app.database.models import Payment, Tariff, User
from app.services.vpn_generator import generate_vpn_key, select_best_server

logger = logging.getLogger(__name__)
app = FastAPI(title="VPN Shop Webhooks")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/yookassa")
async def yookassa_webhook(request: Request) -> dict:
    """Handle ЮKassa payment.succeeded notification."""
    try:
        body = await request.json()
    except Exception:
        return {"error": "invalid json"}

    event = body.get("event", "")
    if event != "payment.succeeded":
        return {"ok": True, "skipped": event}

    obj = body.get("object", {})
    payment_id = obj.get("id", "")
    if not payment_id:
        return {"error": "no payment id"}

    async with async_session() as session:
        result = await session.execute(
            select(Payment).where(Payment.payment_id == payment_id)
        )
        pmt = result.scalar_one_or_none()
        if not pmt:
            logger.warning("Payment %s not found in DB", payment_id)
            return {"error": "not found"}

        if pmt.status == "paid":
            return {"ok": True, "already": True}

        pmt.status = "paid"
        user = await session.get(User, pmt.user_id)
        tariff = await session.get(Tariff, pmt.tariff_id) if pmt.tariff_id else None
        if not user or not tariff:
            await session.commit()
            return {"error": "missing user/tariff"}

        server = await select_best_server(session)
        if not server:
            await session.commit()
            logger.error("No servers available for payment %s", payment_id)
            return {"error": "no servers"}

        try:
            await generate_vpn_key(session, user, tariff, server)
        except Exception as exc:
            logger.error("VPN generation failed via webhook: %s", exc)
            await session.commit()
            return {"error": str(exc)}

        await session.commit()

    return {"ok": True}
