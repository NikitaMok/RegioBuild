from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class InfoFlow(StatesGroup):
    waiting_business_type = State()
    waiting_region = State()


class CompareFlow(StatesGroup):
    waiting_business_type = State()
    waiting_region_a = State()
    waiting_region_b = State()
