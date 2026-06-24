"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str | None) -> list[int]:
    """Parse a comma/space separated list of admin ids into integers."""
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: list[int] = field(default_factory=list)
    payment_provider_token: str = ""
    currency: str = "RUB"
    database_path: str = "vpn_bot.db"

    @property
    def demo_payments(self) -> bool:
        """When no provider token is set the bot runs payments in demo mode."""
        return not self.payment_provider_token

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token or bot_token == "your_telegram_bot_token_here":
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and fill in BOT_TOKEN "
            "(get one from @BotFather)."
        )

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_ID"))
    if not admin_ids:
        raise RuntimeError(
            "ADMIN_ID is not set. Add your numeric Telegram id to .env "
            "(get it from @userinfobot)."
        )

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        payment_provider_token=os.getenv("PAYMENT_PROVIDER_TOKEN", "").strip(),
        currency=os.getenv("CURRENCY", "RUB").strip() or "RUB",
        database_path=os.getenv("DATABASE_PATH", "vpn_bot.db").strip() or "vpn_bot.db",
    )
