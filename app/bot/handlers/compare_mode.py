"""Режим сравнения требований между двумя регионами."""

from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.api_client import ApiClientError, request_compare
from app.bot.keyboards import cancel_keyboard, main_menu_keyboard, region_keyboard, response_keyboard
from app.bot.states import CompareFlow
from app.core.regions import get_region

router = Router(name="compare_mode")


@router.callback_query(F.data == "mode:compare")
async def start_compare_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CompareFlow.waiting_business_type)
    await callback.message.edit_text(
        "Напишите тип бизнеса, который вас интересует (например: кафе, автосервис, склад).",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(CompareFlow.waiting_business_type)
async def receive_business_type(message: Message, state: FSMContext) -> None:
    await state.update_data(business_type=message.text.strip())
    await state.set_state(CompareFlow.waiting_region_a)
    await message.answer("Выберите первый регион:", reply_markup=region_keyboard("region_a"))


@router.callback_query(CompareFlow.waiting_region_a, F.data.startswith("region_a:"))
async def receive_region_a(callback: CallbackQuery, state: FSMContext) -> None:
    region_a = callback.data.split(":", 1)[1]
    await state.update_data(region_a=region_a)
    await state.set_state(CompareFlow.waiting_region_b)
    await callback.message.edit_text(
        "Выберите второй регион для сравнения:",
        reply_markup=region_keyboard("region_b", exclude_code=region_a),
    )
    await callback.answer()


@router.callback_query(CompareFlow.waiting_region_b, F.data.startswith("region_b:"))
async def receive_region_b(callback: CallbackQuery, state: FSMContext) -> None:
    region_b = callback.data.split(":", 1)[1]
    data = await state.get_data()
    business_type = data["business_type"]
    region_a = data["region_a"]
    region_a_name = get_region(region_a).display_name
    region_b_name = get_region(region_b).display_name

    await callback.message.edit_text(
        f"Сравниваю требования для «{html.escape(business_type)}»: "
        f"{region_a_name} и {region_b_name}, минуту..."
    )
    await callback.answer()

    try:
        answer = await request_compare(business_type, region_a, region_b)
    except ApiClientError as exc:
        await callback.message.answer(f"⚠️ {exc}", reply_markup=main_menu_keyboard())
    else:
        keyboard = response_keyboard(answer.query_log_id) if answer.query_log_id else main_menu_keyboard()
        await callback.message.answer(answer.response_text, reply_markup=keyboard)

    await state.clear()
