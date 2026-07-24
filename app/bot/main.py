"""Запуск: python -m app.bot.main (long polling)."""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from app.bot.handlers import common, compare_mode, feedback, info_mode
from app.bot.profile import BOT_DESCRIPTION, BOT_SHORT_DESCRIPTION
from app.core.config import get_settings


async def _publish_bot_profile(bot: Bot) -> None:
    """Карточка «Что умеет этот бот?» — иначе у нового пользователя пустой экран."""
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)
            await bot.set_my_description(BOT_DESCRIPTION)
            logger.info("описание бота в Telegram обновлено")
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(f"попытка {attempt}/3 обновить описание бота: {exc}")
            await asyncio.sleep(1.5 * attempt)
    logger.error(
        f"не удалось опубликовать описание бота в Telegram после 3 попыток: {last_exc}. "
        "У новых пользователей экран до /start будет пустым."
    )


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не задан в .env. Токен выдаёт @BotFather.")
        sys.exit(1)

    if len(BOT_DESCRIPTION) > 512:
        logger.error(f"BOT_DESCRIPTION слишком длинный: {len(BOT_DESCRIPTION)} > 512")
        sys.exit(1)
    if len(BOT_SHORT_DESCRIPTION) > 120:
        logger.error(
            f"BOT_SHORT_DESCRIPTION слишком длинный: {len(BOT_SHORT_DESCRIPTION)} > 120"
        )
        sys.exit(1)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await _publish_bot_profile(bot)

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
