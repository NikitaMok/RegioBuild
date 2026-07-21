from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import query_menu_keyboard, rules_keyboard, start_menu_keyboard
from app.core.legal import DISCLAIMER_TEXT, LEGAL_BOUNDARIES_HTML

router = Router(name="common")

WELCOME_TEXT = (
    "Привет! Я RegioBuild — справочный помощник по региональным строительным "
    "нормативам (РНГП/ТСН) для коммерческого размещения.\n\n"
    f"{LEGAL_BOUNDARIES_HTML}\n\n"
    "Сначала откройте «Обязательно к прочтению» — там ограничения и как "
    "правильно спрашивать."
)

RULES_TEXT = (
    "<b>Как я работаю</b>\n\n"
    "Сравниваю <b>региональные</b> нормативы градостроительного проектирования "
    "(РНГП / ТСН) — акты субъектов РФ — и опираюсь на федеральный фон "
    "(СП 42, выдержки 123-ФЗ/СанПиН).\n\n"
    f"{LEGAL_BOUNDARIES_HTML}\n\n"
    "<b>Чего я не учитываю</b>\n"
    "Муниципальный уровень (местные НГП, ПЗЗ) часто жёстче регионального. "
    "Я на него не смотрю — перед решением сверьте требования в администрации "
    "города/района.\n\n"
    "<b>Как спрашивать</b>\n"
    "1. Тип бизнеса коротко: «кафе», «автомойка», «склад».\n"
    "2. Один регион («Требования в регионе») или два («Сравнить два региона»).\n"
    "3. В ответе есть акт, номер пункта и ссылка на первоисточник. "
    "<b>Откройте и сверьте сами</b> (или покажите юристу).\n\n"
    "<b>Про точность</b>\n"
    "Цитаты программно сверяются с найденными фрагментами индекса; "
    "при слабой опоре помощник отказывается выдумывать. После ответа можно "
    "поставить 👍/👎."
)

HELP_TEXT = (
    "Доступные режимы:\n\n"
    "📍 <b>Требования в регионе</b> — требования для типа бизнеса в одном регионе.\n\n"
    "🔀 <b>Сравнить два региона</b> — разница требований между двумя регионами.\n\n"
    "Команды: /start — меню, /help — эта справка."
    f"{DISCLAIMER_TEXT}"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=start_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.callback_query(F.data == "show_rules")
async def show_rules(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(RULES_TEXT, reply_markup=rules_keyboard())
    await callback.answer()


@router.callback_query(F.data == "show_query_menu")
async def show_query_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Выберите режим работы:", reply_markup=query_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=start_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Отменено. Выберите режим:", reply_markup=query_menu_keyboard())
    await callback.answer()
