"""Automatic notifications — expiry warnings and deactivation."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from app.database.database import async_session
from app.database.models import Subscription, User

logger = logging.getLogger(__name__)


async def check_expiring_subscriptions(bot: Bot) -> None:
    """Notify users whose subscriptions expire within 3 days."""
    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=3)

    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.is_active.is_(True),
                Subscription.expire_date > now,
                Subscription.expire_date <= soon,
            )
        )
        subs = list(result.scalars().all())

        for sub in subs:
            user = await session.get(User, sub.user_id)
            if not user:
                continue
            days_left = (sub.expire_date - now).days
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"⏰ Ваша VPN-подписка заканчивается через {days_left} дн.\n"
                    f"Продлите, чтобы не потерять доступ.",
                )
            except Exception:
                logger.debug("Failed to notify user %s", user.telegram_id)


async def deactivate_expired(bot: Bot) -> None:
    """Deactivate expired subscriptions and notify users."""
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.is_active.is_(True), Subscription.expire_date <= now
            )
        )
        expired = list(result.scalars().all())

        for sub in expired:
            sub.is_active = False
            user = await session.get(User, sub.user_id)
            if user:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        "❌ Ваша VPN-подписка истекла. VPN отключён.\n"
                        "Нажмите /start чтобы продлить.",
                    )
                except Exception:
                    pass
        await session.commit()


async def notification_loop(bot: Bot) -> None:
    """Background loop: check every hour for expiring/expired subs."""
    while True:
        try:
            await check_expiring_subscriptions(bot)
            await deactivate_expired(bot)
        except Exception as exc:
            logger.error("Notification loop error: %s", exc)
        await asyncio.sleep(3600)
