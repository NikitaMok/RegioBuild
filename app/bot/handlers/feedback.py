"""Реакция пользователя на ответ бота (👍/👎 под сообщением с требованиями)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.api_client import send_feedback
from app.bot.keyboards import main_menu_keyboard

router = Router(name="feedback")

THANKS_TEXT = "Очень рад был помочь! 😊"
APOLOGY_TEXT = (
    "Жаль, что ответ не подошёл. Извините — я пока учусь и стараюсь становиться "
    "точнее с каждым запросом. Попробуйте, пожалуйста, переформулировать вопрос "
    "или вернуться немного позже 🙏"
)


@router.callback_query(F.data.startswith("feedback:"))
async def handle_feedback(callback: CallbackQuery) -> None:
    _, vote, query_log_id = callback.data.split(":", 2)
    await send_feedback(query_log_id, vote)

    # кнопки фидбека убираем, чтобы нельзя было проголосовать повторно, а
    # переход к следующему действию показываем только теперь, отдельным
    # сообщением — до реакции пользователя эти кнопки ему не нужны и только
    # создают впечатление, что бот не дождался ответа на свой же вопрос
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        THANKS_TEXT if vote == "up" else APOLOGY_TEXT,
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()
