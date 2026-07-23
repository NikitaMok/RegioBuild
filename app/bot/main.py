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

# Карточка «Что умеет этот бот?» в Telegram (не путать с ответом на /start).
BOT_SHORT_DESCRIPTION = (
    "Справка по РНГП/ТСН пяти субъектов РФ и федеральному нормативному фону"
)
BOT_DESCRIPTION = (
    "RegioBuild — справочный сервис по региональным нормативам градостроительного "
    "проектирования (РНГП/ТСН) и федеральному фону для объектов капитального "
    "строительства.\n\n"
    "Команда /start открывает меню. Ответ носит справочный характер и не заменяет "
    "юридическую консультацию; муниципальные ПЗЗ в индекс не входят."
)


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не задан в .env. Токен выдаёт @BotFather.")
        sys.exit(1)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)
        await bot.set_my_description(BOT_DESCRIPTION)
    except Exception as exc:
        logger.warning(f"не удалось обновить описание бота в Telegram: {exc}")

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
