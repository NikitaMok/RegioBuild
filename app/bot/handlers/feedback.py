"""Кнопки 👍/👎 под ответом с требованиями."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.api_client import send_feedback
from app.bot.keyboards import start_menu_keyboard

router = Router(name="feedback")

THANKS_TEXT = (
    "Искренне благодарим Вас за столь высокую оценку нашей работы — для нас это "
    "особенно ценно. Рады, что подготовленная справка по нормативным требованиям "
    "оказалась полезной, и искренне рады были оказать Вам содействие. При "
    "последующих вопросах по региональным и федеральным нормативам "
    "градостроительного проектирования будем рады вновь помочь."
)
APOLOGY_TEXT = (
    "Благодарим за замечание. Сервис находится в стадии развития: корпус "
    "региональных и федеральных актов пополняется, а формулировки ответов "
    "уточняются по результатам обратной связи. Просим вернуться позднее — "
    "постараемся подготовить более точную и полную справку по вашему запросу."
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
