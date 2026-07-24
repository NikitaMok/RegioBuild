from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import query_menu_keyboard, rules_keyboard, start_menu_keyboard
from app.core.legal import DISCLAIMER_TEXT, LEGAL_BOUNDARIES_HTML

router = Router(name="common")

# Короткое приветствие после /start — без дубля карточки бота и без полного текста правил.
WELCOME_TEXT = (
    "Уважаемый пользователь!\n\n"
    "По вашему запросу сервис формирует структурированный перечень требований "
    "к объекту капитального строительства по региональным нормативам "
    "градостроительного проектирования (РНГП/ТСН) и по применимым федеральным "
    "нормам — с указанием реквизитов актов и номеров пунктов (статей, частей, "
    "таблиц), чтобы не приходилось самостоятельно разбирать полный текст "
    "нормативных правовых актов.\n\n"
    "Перед первым запросом ознакомьтесь с разделом «Обязательно к прочтению»: "
    "в нём изложены условия использования сервиса и порядок подготовки запроса."
)

# Полные условия — только здесь; не пересекаются с WELCOME_TEXT и карточкой бота.
RULES_TEXT = (
    "По запросу сервис формирует перечень применимых требований к объекту "
    "капитального строительства на основании <b>региональных</b> нормативов "
    "градостроительного проектирования (РНГП/ТСН) пяти субъектов Российской "
    "Федерации — Московская область, Краснодарский край, Свердловская область, "
    "Новосибирская область, Республика Татарстан — а также федерального "
    "нормативного фона: Градостроительный кодекс РФ, СП 42.13330, Федеральный "
    "закон № 123-ФЗ «Технический регламент о требованиях пожарной безопасности», "
    "СанПиН — в объёме материалов, включённых в сервис. В ответе указываются "
    "реквизиты нормативного правового акта и номер пункта (статьи, части, таблицы).\n\n"
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
    "📍 <b>Требования в регионе</b> — перечень требований "
    "к объекту капитального строительства в одном субъекте Российской Федерации "
    "со ссылками на пункты нормативных правовых актов.\n\n"
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
