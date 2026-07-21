"""Режим: сравнение требований между двумя субъектами РФ."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.api_client import ApiClientError, request_compare
from app.bot.keyboards import cancel_keyboard, main_menu_keyboard, region_keyboard, response_keyboard
from app.bot.messaging import answer_html_chunks
from app.bot.states import CompareFlow
from app.core.business_type import looks_like_business_query

router = Router(name="compare_mode")

ASK_OBJECT_TEXT = (
    "Укажите объект капитального строительства, "
    "требования к которому необходимо сравнить "
    "(например: кафе, автосервис, склад и т.д.)."
)

INVALID_BUSINESS_REPLY = (
    "Формулировка не позволяет определить объект. Укажите объект капитального "
    "строительства кратко, например: кафе, автомойка, склад, медицинский центр и т.д."
)

WAIT_TEXT = "Сравниваю требования по регионам, подождите…"


@router.callback_query(F.data == "mode:compare")
async def start_compare_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CompareFlow.waiting_business_type)
    await callback.message.edit_text(ASK_OBJECT_TEXT, reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(CompareFlow.waiting_business_type)
async def receive_business_type(message: Message, state: FSMContext) -> None:
    business_type = (message.text or "").strip()
    if not looks_like_business_query(business_type):
        await message.answer(INVALID_BUSINESS_REPLY, reply_markup=cancel_keyboard())
        return

    await state.update_data(business_type=business_type)
    await state.set_state(CompareFlow.waiting_region_a)
    await message.answer(
        "Выберите первый субъект Российской Федерации:",
        reply_markup=region_keyboard("region_a"),
    )


@router.callback_query(CompareFlow.waiting_region_a, F.data.startswith("region_a:"))
async def receive_region_a(callback: CallbackQuery, state: FSMContext) -> None:
    region_a = callback.data.split(":", 1)[1]
    await state.update_data(region_a=region_a)
    await state.set_state(CompareFlow.waiting_region_b)
    await callback.message.edit_text(
        "Выберите второй субъект Российской Федерации для сравнения:",
        reply_markup=region_keyboard("region_b", exclude_code=region_a),
    )
    await callback.answer()


@router.callback_query(CompareFlow.waiting_region_b, F.data.startswith("region_b:"))
async def receive_region_b(callback: CallbackQuery, state: FSMContext) -> None:
    region_b = callback.data.split(":", 1)[1]
    data = await state.get_data()
    business_type = data["business_type"]
    region_a = data["region_a"]
    telegram_user_id = str(callback.from_user.id) if callback.from_user else None

    await callback.message.edit_text(WAIT_TEXT)
    await callback.answer()

    try:
        answer = await request_compare(
            business_type,
            region_a,
            region_b,
            telegram_user_id=telegram_user_id,
        )
    except ApiClientError as exc:
        await callback.message.answer(f"⚠️ {exc}", reply_markup=main_menu_keyboard())
    else:
        keyboard = response_keyboard(answer.query_log_id) if answer.query_log_id else main_menu_keyboard()
        await answer_html_chunks(callback.message, answer.response_text, reply_markup=keyboard)

    await state.clear()
