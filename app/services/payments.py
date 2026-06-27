"""Payment service — ЮKassa integration with SBP/QR support."""

from __future__ import annotations

import io
import uuid as uuid_lib
from typing import Any

import qrcode
from yookassa import Configuration, Payment as YKPayment

from app.config.settings import settings


class PaymentError(RuntimeError):
    pass


def _configure() -> None:
    if settings.yookassa_shop_id and settings.yookassa_secret_key:
        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret_key


async def create_payment(
    amount: float,
    description: str,
    metadata: dict[str, Any] | None = None,
    confirmation_type: str = "redirect",
) -> dict[str, str]:
    """Create a ЮKassa payment.

    confirmation_type:
        'redirect' — standard card payment (returns confirmation_url)
        'qr' — SBP payment (returns qr_data for QR generation)
    """
    _configure()
    if not settings.yookassa_shop_id:
        raise PaymentError("ЮKassa not configured (YOOKASSA_SHOP_ID missing)")

    idempotency_key = str(uuid_lib.uuid4())

    if confirmation_type == "qr":
        confirmation = {"type": "qr"}
    else:
        confirmation = {"type": "redirect", "return_url": "https://t.me"}

    payment = YKPayment.create(
        {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": confirmation,
            "capture": True,
            "description": description,
            "metadata": metadata or {},
            "payment_method_data": {"type": "sbp"} if confirmation_type == "qr" else None,
        },
        idempotency_key,
    )

    result: dict[str, str] = {"id": payment.id}

    if payment.confirmation:
        if hasattr(payment.confirmation, "confirmation_url") and payment.confirmation.confirmation_url:
            result["confirmation_url"] = payment.confirmation.confirmation_url
        if hasattr(payment.confirmation, "confirmation_data") and payment.confirmation.confirmation_data:
            result["qr_data"] = payment.confirmation.confirmation_data

    return result


async def check_payment(payment_id: str) -> str:
    """Return payment status: pending / succeeded / canceled."""
    _configure()
    payment = YKPayment.find_one(payment_id)
    return payment.status or "pending"


def generate_payment_qr(qr_data: str) -> io.BytesIO:
    """Generate QR code for SBP payment."""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
