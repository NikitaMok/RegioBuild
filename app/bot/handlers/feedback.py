"""Кнопки 👍/👎 под ответом с требованиями."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.api_client import send_feedback
from app.bot.keyboards import start_menu_keyboard

router = Router(name="feedback")

THANKS_TEXT = (
    "Искренне благодарим Вас за столь высокую оценку нашей работы — для нас это "
    "особенно ценно!\n"
    "Надеемся, что подготовленная справка по нормативным требованиям оказалась "
    "полезной, и искренне рады были оказать Вам содействие. В случае появления "
    "у Вас новых вопросов по региональным и федеральным нормативам "
    "градостроительного проектирования будем рады вновь помочь!"
)
APOLOGY_TEXT = (
    "Благодарим Вас за обратную связь.\n"
    "В настоящее время наш сервис находится в стадии развития: база региональных "
    "и федеральных нормативных правовых актов пополняется, а формулировки "
    "ответов систематически улучшаются.\n"
    "Поэтому просим Вас дать нам ещё один шанс в будущем и мы обязательно "
    "подготовим максимально точную справку по Вашему запросу!"
)


@router.callback_query(F.data.startswith("feedback:"))
async def handle_feedback(callback: CallbackQuery) -> None:
    _, vote, query_log_id = callback.data.split(":", 2)
    await send_feedback(query_log_id, vote)

    # убираем кнопки, чтобы не голосовали дважды; меню — отдельным сообщением
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        THANKS_TEXT if vote == "up" else APOLOGY_TEXT,
        reply_markup=start_menu_keyboard(),
    )
    await callback.answer()
