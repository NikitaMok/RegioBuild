"""Информационный режим: требования для объекта в одном регионе."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.api_client import ApiClientError, request_info
from app.bot.keyboards import cancel_keyboard, main_menu_keyboard, region_keyboard, response_keyboard
from app.bot.messaging import answer_html_chunks
from app.bot.states import InfoFlow
from app.core.business_type import looks_like_business_query

router = Router(name="info_mode")

ASK_OBJECT_TEXT = (
    "Укажите объект капитального строительства или иной объект размещения, "
    "требования к которому необходимо определить "
    "(например: кафе, автосервис, склад и т.д.)."
)

INVALID_BUSINESS_REPLY = (
    "Формулировка не позволяет определить объект размещения. Укажите объект кратко, "
    "например: кафе, автомойка, склад, медицинский центр и т.д."
)

WAIT_TEXT = "Формирую правовую справку по запросу. Пожалуйста, подождите."


@router.callback_query(F.data == "mode:info")
async def start_info_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InfoFlow.waiting_business_type)
    await callback.message.edit_text(ASK_OBJECT_TEXT, reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(InfoFlow.waiting_business_type)
async def receive_business_type(message: Message, state: FSMContext) -> None:
    business_type = (message.text or "").strip()
    if not looks_like_business_query(business_type):
        await message.answer(INVALID_BUSINESS_REPLY, reply_markup=cancel_keyboard())
        return

    await state.update_data(business_type=business_type)
    await state.set_state(InfoFlow.waiting_region)
    await message.answer("Выберите субъект Российской Федерации:", reply_markup=region_keyboard("region"))


@router.callback_query(InfoFlow.waiting_region, F.data.startswith("region:"))
async def receive_region(callback: CallbackQuery, state: FSMContext) -> None:
    region_code = callback.data.split(":", 1)[1]
    data = await state.get_data()
    business_type = data["business_type"]
    telegram_user_id = str(callback.from_user.id) if callback.from_user else None

    await callback.message.edit_text(WAIT_TEXT)
    await callback.answer()

    try:
        answer = await request_info(business_type, region_code, telegram_user_id=telegram_user_id)
    except ApiClientError as exc:
        await callback.message.answer(f"⚠️ {exc}", reply_markup=main_menu_keyboard())
    else:
        keyboard = response_keyboard(answer.query_log_id) if answer.query_log_id else main_menu_keyboard()
        await answer_html_chunks(callback.message, answer.response_text, reply_markup=keyboard)

    await state.clear()
