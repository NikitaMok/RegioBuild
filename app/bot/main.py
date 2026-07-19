"""Запуск: python -m app.bot.main (long polling)."""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from app.bot.handlers import common, compare_mode, feedback, info_mode
from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не задан в .env. Токен выдаёт @BotFather.")
        sys.exit(1)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(common.router)
    dispatcher.include_router(info_mode.router)
    dispatcher.include_router(compare_mode.router)
    dispatcher.include_router(feedback.router)

    logger.info(f"бот запущен, API_BASE_URL={settings.api_base_url}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
