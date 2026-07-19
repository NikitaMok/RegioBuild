from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import query_menu_keyboard, rules_keyboard, start_menu_keyboard

router = Router(name="common")

WELCOME_TEXT = (
    "👋 Привет! Я RegioBuild — помогаю бизнесу разобраться в региональных "
    "строительных нормативах при открытии или расширении в новый регион.\n\n"
    "Перед тем как задавать вопросы, пожалуйста, откройте «Обязательно к "
    "прочтению» — там пара минут чтения, но это важно понять, чтобы не "
    "принять мой ответ за 100% истину без проверки."
)

RULES_TEXT = (
    "<b>Как я работаю</b>\n\n"
    "Я сравниваю <b>региональные</b> нормативы градостроительного "
    "проектирования (РНГП / ТСН) — это акты, которые принимают органы власти "
    "субъекта РФ (области, края) и которые задают требования к застройке "
    "для всей территории региона: сроки, документы, подключение к сетям, "
    "состав проекта.\n\n"
    "<b>⚠️ Важно понимать, чего я не проверяю</b>\n"
    "Помимо регионального уровня, в конкретном муниципальном образовании "
    "(город, район, поселение) почти всегда есть свои местные нормативы "
    "градостроительного проектирования и правила землепользования и "
    "застройки (ПЗЗ) — они могут добавлять более строгие или отдельные "
    "требования сверх регионального акта. Я <b>не</b> учитываю муниципальный "
    "уровень — обязательно уточните его отдельно в администрации нужного "
    "города/района, прежде чем принимать решение.\n\n"
    "<b>Как правильно спрашивать</b>\n"
    "1. В строке типа бизнеса пишите коротко и по делу: «кафе», "
    "«автомойка», «склад». Можно и целым предложением — я попробую понять "
    "суть, но короткая формулировка надёжнее.\n"
    "2. Выберите один регион («Требования в регионе») или два региона для "
    "сравнения («Сравнить два региона»).\n"
    "3. В ответе я указываю название нормативного акта и номер конкретного "
    "пункта, из которого взят факт. <b>Обязательно откройте первоисточник и "
    "сверьте пункт сами</b> (или покажите юристу) — не принимайте решений "
    "только на основании моего ответа.\n\n"
    "<b>Почему это важно</b>\n"
    "Я — учебный проект, который пока обучается отвечать точнее. Я стараюсь "
    "не придумывать факты и опираюсь только на текст норматива, но ошибки "
    "и неполные ответы всё ещё возможны. Поэтому после каждого ответа я "
    "спрашиваю, помог ли он — это помогает мне становиться лучше."
)

HELP_TEXT = (
    "Доступные режимы:\n\n"
    "📍 <b>Требования в регионе</b> — узнать требования (сроки, документы, "
    "подключение к сетям, состав проекта) для вашего типа бизнеса в одном регионе.\n\n"
    "🔀 <b>Сравнить два региона</b> — увидеть структурированную разницу требований "
    "между двумя регионами для одного типа бизнеса.\n\n"
    "Команды: /start — главное меню, /help — эта справка."
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
