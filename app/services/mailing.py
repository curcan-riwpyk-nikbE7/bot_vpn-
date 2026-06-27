"""Mailing service — broadcast messages to user groups."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Subscription, User

logger = logging.getLogger(__name__)

TargetGroup = Literal["all", "active", "expiring"]


async def get_target_users(
    session: AsyncSession, group: TargetGroup
) -> list[int]:
    """Return list of telegram_ids matching the target group."""
    if group == "all":
        result = await session.execute(
            select(User.telegram_id).where(User.is_blocked.is_(False))
        )
    elif group == "active":
        now = datetime.now(timezone.utc)
        sub_stmt = (
            select(Subscription.user_id)
            .where(Subscription.is_active.is_(True), Subscription.expire_date > now)
            .distinct()
        )
        result = await session.execute(
            select(User.telegram_id).where(User.id.in_(sub_stmt), User.is_blocked.is_(False))
        )
    elif group == "expiring":
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=3)
        sub_stmt = (
            select(Subscription.user_id)
            .where(
                Subscription.is_active.is_(True),
                Subscription.expire_date > now,
                Subscription.expire_date <= soon,
            )
            .distinct()
        )
        result = await session.execute(
            select(User.telegram_id).where(User.id.in_(sub_stmt), User.is_blocked.is_(False))
        )
    else:
        return []

    return [row[0] for row in result.all()]


async def broadcast(
    bot: Bot, user_ids: list[int], text: str, *, delay: float = 0.05
) -> tuple[int, int]:
    """Send text to all user_ids. Returns (sent, failed)."""
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
            logger.debug("Failed to send to %s", uid)
        await asyncio.sleep(delay)
    return sent, failed
