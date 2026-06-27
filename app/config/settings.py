"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: str = ""
    admin_ids: list[int] = []
    webhook_url: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://vpn_bot:vpn_bot_secret@postgres:5432/vpn_shop"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # ЮKassa
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_webhook_secret: str = ""
    payment_provider_token: str = ""

    # 3X-UI
    xui_flow: str = "xtls-rprx-vision"
    xui_verify_ssl: bool = False

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # Bot appearance defaults
    service_name: str = "VPN SERVICE"
    support_username: str = "@support"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
