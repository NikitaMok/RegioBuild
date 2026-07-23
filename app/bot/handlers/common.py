from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import query_menu_keyboard, rules_keyboard, start_menu_keyboard
from app.core.legal import DISCLAIMER_TEXT, LEGAL_BOUNDARIES_HTML

router = Router(name="common")

WELCOME_TEXT = (
    "<b>RegioBuild</b>\n\n"
    "Уважаемый пользователь!\n\n"
    "Сервис предназначен для справочного ознакомления с региональными "
    "нормативами градостроительного проектирования (РНГП/ТСН) пяти субъектов "
    "Российской Федерации, а также с применимыми положениями федерального "
    "законодательства и подзаконных актов (включая Градостроительный кодекс РФ, "
    "СП 42.13330, Федеральный закон № 123-ФЗ и СанПиН) в отношении объектов "
    "капитального строительства.\n\n"
    f"{LEGAL_BOUNDARIES_HTML}\n\n"
    "Перед направлением первого запроса рекомендуем ознакомиться с разделом "
    "«Обязательно к прочтению»: в нём изложены правовые пределы использования "
    "сервиса и порядок подготовки запроса."
)

RULES_TEXT = (
    "<b>Состав нормативных материалов:</b>\n\n"
    "Сервис обеспечивает работу с <b>региональными</b> нормативами "
    "градостроительного проектирования (РНГП/ТСН) пяти субъектов Российской "
    "Федерации (Московская область, Краснодарский край, Свердловская область, "
    "Новосибирская область, Республика Татарстан), а также с положениями "
    "федерального уровня: Градостроительный кодекс РФ, СП 42.13330, "
    "Федеральный закон № 123-ФЗ «Технический регламент о требованиях пожарной "
    "безопасности», СанПиН — в объёме нормативных материалов, включённых в сервис.\n\n"
    f"{LEGAL_BOUNDARIES_HTML}\n\n"
    "<b>Что не охватывается сервисом:</b>\n"
    "Нормативные правовые акты муниципального уровня (местные нормативы, "
    "правила землепользования и застройки и иные акты органов местного "
    "самоуправления) могут устанавливать более строгие требования, чем "
    "региональные и федеральные нормы. Перед принятием решения рекомендуем "
    "дополнительно сверить требования в уполномоченном органе соответствующего "
    "муниципального образования.\n\n"
    "<b>Порядок обращения:</b>\n"
    "1. Укажите тип объекта капитального строительства кратко "
    "(например: «кафе», «автомойка», «склад» и т.д.).\n"
    "2. Выберите режим: требования по одному субъекту Российской Федерации "
    "либо сравнение двух субъектов.\n"
    "3. В ответе приводятся реквизиты нормативного правового акта и номер "
    "пункта (статьи, части). Рекомендуем сверить указанные положения по "
    "официальному тексту соответствующего акта.\n\n"
    "<b>О достоверности сведений:</b>\n"
    "Указание пунктов и статей сопровождается сопоставлением с текстами "
    "нормативных правовых актов, доступных сервису. При отсутствии "
    "достаточных оснований в указанных источниках сервис воздерживается от "
    "формулирования требования, чтобы исключить необоснованные выводы. "
    "После получения ответа Вы можете оценить его полезность (👍/👎)."
)

HELP_TEXT = (
    "Доступные режимы работы:\n\n"
    "📍 <b>Требования в регионе</b> — справочные сведения о требованиях "
    "к объекту капитального строительства в одном субъекте Российской Федерации.\n\n"
    "🔀 <b>Сравнить два региона</b> — сопоставление требований двух субъектов "
    "Российской Федерации.\n\n"
    "Команды: /start — главное меню, /help — настоящая справка."
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
    await callback.message.edit_text(
        "Выберите режим работы:", reply_markup=query_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=start_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=start_menu_keyboard())
    await callback.answer()
