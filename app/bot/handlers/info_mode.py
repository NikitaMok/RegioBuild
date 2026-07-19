"""Информационный режим: требования для бизнеса в одном регионе."""

from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.api_client import ApiClientError, request_info
from app.bot.keyboards import cancel_keyboard, main_menu_keyboard, region_keyboard, response_keyboard
from app.bot.states import InfoFlow
from app.core.regions import get_region

router = Router(name="info_mode")


@router.callback_query(F.data == "mode:info")
async def start_info_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InfoFlow.waiting_business_type)
    await callback.message.edit_text(
        "Напишите тип бизнеса, который вас интересует (например: кафе, автосервис, склад).",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(InfoFlow.waiting_business_type)
async def receive_business_type(message: Message, state: FSMContext) -> None:
    await state.update_data(business_type=message.text.strip())
    await state.set_state(InfoFlow.waiting_region)
    await message.answer("Выберите регион:", reply_markup=region_keyboard("region"))


@router.callback_query(InfoFlow.waiting_region, F.data.startswith("region:"))
async def receive_region(callback: CallbackQuery, state: FSMContext) -> None:
    region_code = callback.data.split(":", 1)[1]
    data = await state.get_data()
    business_type = data["business_type"]
    region_name = get_region(region_code).display_name

    await callback.message.edit_text(
        f"Ищу требования для «{html.escape(business_type)}» в регионе {region_name}, минуту..."
    )
    await callback.answer()

    try:
        answer = await request_info(business_type, region_code)
    except ApiClientError as exc:
        await callback.message.answer(f"⚠️ {exc}", reply_markup=main_menu_keyboard())
    else:
        keyboard = response_keyboard(answer.query_log_id) if answer.query_log_id else main_menu_keyboard()
        await callback.message.answer(answer.response_text, reply_markup=keyboard)

    await state.clear()
