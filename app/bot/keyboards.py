from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.regions import REGIONS


def start_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Обязательно к прочтению", callback_data="show_rules")],
        [InlineKeyboardButton(text="🔎 Узнать требования", callback_data="show_query_menu")],
    ])


def rules_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Узнать требования", callback_data="show_query_menu")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_start")],
    ])


def query_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Требования в одном регионе", callback_data="mode:info")],
        [InlineKeyboardButton(text="🔀 Сравнить два региона", callback_data="mode:compare")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_start")],
    ])


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для перехода к следующему запросу: показываем после того как
    пользователь отреагировал на фидбек (или сразу, если сохранить фидбек
    не удалось и кнопок 👍/👎 не было вовсе)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Требования в регионе", callback_data="mode:info")],
        [InlineKeyboardButton(text="🔀 Сравнить два региона", callback_data="mode:compare")],
    ])


def response_keyboard(query_log_id: str) -> InlineKeyboardMarkup:
    """Клавиатура сразу под ответом агента — только фидбек. Кнопки перехода к
    следующему действию показываем отдельно, только после реакции 👍/👎 (см.
    app/bot/handlers/feedback.py) — иначе бот одновременно спрашивает, помог ли
    ответ, и предлагает начать заново, что путает и выглядит нелогично."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 Помогло", callback_data=f"feedback:up:{query_log_id}"),
            InlineKeyboardButton(text="👎 Не помогло", callback_data=f"feedback:down:{query_log_id}"),
        ],
    ])


def region_keyboard(callback_prefix: str, exclude_code: str | None = None) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=region.display_name, callback_data=f"{callback_prefix}:{region.code}")]
        for region in REGIONS.values()
        if region.code != exclude_code
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
