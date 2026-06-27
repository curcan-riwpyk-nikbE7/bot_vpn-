"""Payment service — ЮKassa integration."""

from __future__ import annotations

import uuid as uuid_lib
from typing import Any

from yookassa import Configuration, Payment as YKPayment

from app.config.settings import settings


class PaymentError(RuntimeError):
    pass


def _configure() -> None:
    if settings.yookassa_shop_id and settings.yookassa_secret_key:
        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret_key


async def create_payment(
    amount: float, description: str, metadata: dict[str, Any] | None = None
) -> dict[str, str]:
    """Create a ЮKassa payment. Returns {id, confirmation_url}."""
    _configure()
    if not settings.yookassa_shop_id:
        raise PaymentError("ЮKassa not configured (YOOKASSA_SHOP_ID missing)")

    idempotency_key = str(uuid_lib.uuid4())
    payment = YKPayment.create(
        {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": "https://t.me"},
            "capture": True,
            "description": description,
            "metadata": metadata or {},
        },
        idempotency_key,
    )
    url = ""
    if payment.confirmation:
        url = payment.confirmation.confirmation_url or ""
    return {"id": payment.id, "confirmation_url": url}


async def check_payment(payment_id: str) -> str:
    """Return payment status: pending / succeeded / canceled."""
    _configure()
    payment = YKPayment.find_one(payment_id)
    return payment.status or "pending"
