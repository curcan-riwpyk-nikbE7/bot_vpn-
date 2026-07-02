"""Referral system — track invites and award bonuses."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Referral, Setting, User

# Default reward tiers: {required_invites: bonus_days}
DEFAULT_TIERS = {3: 7, 10: 30}


async def get_referral_link(bot_username: str, user_id: int) -> str:
    """Build a referral link for the user."""
    return f"https://t.me/{bot_username}?start=ref{user_id}"


async def register_referral(session: AsyncSession, referrer_tg_id: int, invited_tg_id: int) -> bool:
    """Record a referral if not already registered. Returns True if new."""
    existing = await session.execute(
        select(Referral).where(Referral.invited_id == invited_tg_id)
    )
    if existing.scalar_one_or_none():
        return False

    referrer = await session.execute(select(User).where(User.telegram_id == referrer_tg_id))
    referrer_user = referrer.scalar_one_or_none()
    if not referrer_user:
        return False

    ref = Referral(referrer_id=referrer_user.id, invited_id=invited_tg_id)
    session.add(ref)
    await session.commit()
    return True


async def check_and_award(session: AsyncSession, referrer_tg_id: int) -> int:
    """Check referral count and award bonus days. Returns days awarded (0 if none new)."""
    referrer = await session.execute(select(User).where(User.telegram_id == referrer_tg_id))
    referrer_user = referrer.scalar_one_or_none()
    if not referrer_user:
        return 0

    count_stmt = select(func.count()).select_from(Referral).where(
        Referral.referrer_id == referrer_user.id
    )
    result = await session.execute(count_stmt)
    count = result.scalar() or 0

    tiers = DEFAULT_TIERS
    # Load custom tiers from settings if available
    tier_setting = await session.execute(select(Setting).where(Setting.key == "referral_tiers"))
    tier_row = tier_setting.scalar_one_or_none()
    if tier_row and tier_row.value:
        import json
        try:
            tiers = {int(k): int(v) for k, v in json.loads(tier_row.value).items()}
        except (ValueError, TypeError):
            pass

    awarded = 0
    for threshold, days in sorted(tiers.items()):
        if count >= threshold:
            awarded = days  # highest tier reached

    # Only award delta between current bonus and what they earned
    already = referrer_user.bonus_days
    if awarded > already:
        referrer_user.bonus_days = awarded
        await session.commit()
        return awarded - already
    return 0


async def get_referral_count(session: AsyncSession, user: User) -> int:
    """Return number of people invited by this user."""
    result = await session.execute(
        select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id)
    )
    return result.scalar() or 0
