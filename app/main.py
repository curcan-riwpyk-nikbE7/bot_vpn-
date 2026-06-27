"""Application entry point — starts bot polling + FastAPI server."""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.admin.webhook import app as fastapi_app
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.client import router as client_router
from app.config.settings import settings
from app.database.database import init_db
from app.services.notifications import notification_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def start_api() -> None:
    """Run FastAPI in background for payment webhooks."""
    config = uvicorn.Config(
        fastapi_app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    logger.info("Initializing database...")
    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin_router)
    dp.include_router(client_router)

    bot_info = await bot.get_me()
    logger.info("Bot started: @%s [%s]", bot_info.username, bot_info.id)
    logger.info("Admins: %s", settings.admin_ids)

    # Start background tasks
    asyncio.create_task(notification_loop(bot))
    asyncio.create_task(start_api())

    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
