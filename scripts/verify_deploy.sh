#!/usr/bin/env bash
# Пост-проверка деплоя: HEAD, health, живой код в контейнере API.
# Без этого «deploy OK» может врать — пользователь видит старый бот.
set -euo pipefail

ROOT="${DEPLOY_PATH:-/opt/regiobuild}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
EXPECTED_SHA="${EXPECTED_SHA:-}"
cd "$ROOT"

fail() {
  echo "VERIFY FAIL: $*" >&2
  exit 1
}

echo "=== verify deploy ==="

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/${DEPLOY_BRANCH:-main}")"
SHORT_LOCAL="$(git rev-parse --short HEAD)"
echo "local HEAD:  $LOCAL_SHA ($SHORT_LOCAL)"
echo "origin/main: $REMOTE_SHA"

if [[ -n "$EXPECTED_SHA" && "$LOCAL_SHA" != "$EXPECTED_SHA" ]]; then
  fail "локальный HEAD ($SHORT_LOCAL) != EXPECTED_SHA (${EXPECTED_SHA:0:7}). Код на сервере не тот, что запушили."
fi

if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then
  fail "локальный HEAD != origin/${DEPLOY_BRANCH:-main}. Сначала git fetch/reset."
fi

# API должен быть healthy
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS -m 10 "http://127.0.0.1:3000/health" | grep -qi ok; then
    echo "health: ok"
    break
  fi
  if [[ "$i" -eq 10 ]]; then
    fail "API /health не отвечает ok за отведённое время"
  fi
  sleep 3
done

# Ключевые пользовательские формулировки — именно в RUNNING контейнере
docker compose -f "$COMPOSE_FILE" --env-file .env exec -T api python - <<'PY'
from app.core.legal import DISCLAIMER_TEXT, LEGAL_BOUNDARIES_HTML
from app.bot.handlers.common import WELCOME_TEXT, RULES_TEXT
from app.bot.profile import BOT_DESCRIPTION, BOT_SHORT_DESCRIPTION
from app.agent.nodes import _render_extraction, _polish_response_text, _MISSING_REGION_VALUE
from app.llm.schemas import ExtractionResult, RequirementItem

errors = []

if "<b>RegioBuild</b>" in WELCOME_TEXT:
    errors.append("WELCOME: лишний заголовок RegioBuild в /start")
if "справочного ознакомления" in WELCOME_TEXT.lower():
    errors.append("WELCOME: устаревшая формулировка «справочного ознакомления»")
if "Правовые пределы использования" in WELCOME_TEXT:
    errors.append("WELCOME: не должно дублировать блок правовых пределов")
if "Уважаемый пользователь!" not in WELCOME_TEXT:
    errors.append("WELCOME: нет обращения")
if "Обязательно к прочтению" not in WELCOME_TEXT:
    errors.append("WELCOME: нет отсылки к правилам")

if "Состав нормативных материалов" in RULES_TEXT:
    errors.append("RULES: заголовок «Состав нормативных материалов» должен быть убран")
if "Правовые пределы использования" in RULES_TEXT or "Правовые пределы использования" in LEGAL_BOUNDARIES_HTML:
    errors.append("RULES: заголовок «Правовые пределы использования» должен быть убран")
if "обеспечивает работу" in RULES_TEXT.lower():
    errors.append("RULES: формулировка «обеспечивает работу» недопустима")
if "формирует перечень" not in RULES_TEXT.lower() and "формирует" not in RULES_TEXT.lower():
    errors.append("RULES: нет формулировки о формировании перечня требований")

if len(BOT_DESCRIPTION) > 512:
    errors.append(f"PROFILE: description слишком длинный ({len(BOT_DESCRIPTION)})")
if len(BOT_SHORT_DESCRIPTION) > 120:
    errors.append(f"PROFILE: short_description слишком длинный ({len(BOT_SHORT_DESCRIPTION)})")
if "формирует перечень требований" not in BOT_DESCRIPTION.lower() and "формирует" not in BOT_DESCRIPTION.lower():
    errors.append("PROFILE: описание бота не отражает выдачу требований")

if "Вышеуказанные сведения носят справочный характер!" not in DISCLAIMER_TEXT:
    errors.append("DISCLAIMER: нет нового заголовка")
if "<i>" not in DISCLAIMER_TEXT:
    errors.append("DISCLAIMER: нет курсива")

text = _render_extraction(
    ExtractionResult(
        region_code="krasnodar_krai",
        business_type="автомойка",
        items=[
            RequirementItem(
                category="сроки_и_документы",
                description="тест",
                citation="1.1",
                source_level="региональный",
            )
        ],
    )
)
if "Региональные требования" not in text:
    errors.append("RENDER: нет «Региональные требования»")
if "Региональный уровень" in text or "Федеральный уровень" in text:
    errors.append("RENDER: старое слово «уровень» всё ещё в ответе")

sample = (
    "В Московской области установлены региональные требования к складам. "
    "В Новосибирской области детальные региональные нормы для складов не установлены; "
    "обязательны только федеральные требования."
)
polished = _polish_response_text(sample)
if "\n\nВ Новосибирской" not in polished:
    errors.append("POLISH: нет абзаца перед вторым субъектом")
if "; обязательны" in polished:
    errors.append("POLISH: точка с запятой перед «обязательны» не заменена")

junk = _polish_response_text("норма\n### /с/ /с/ /с/ /с/\nконец")
if "/с/" in junk or "###" in junk:
    errors.append("POLISH: артефакт /с/ не вырезается")

if "специальные требования по указанному вопросу не установлены" not in _MISSING_REGION_VALUE.lower():
    errors.append("MISSING: нет юридической фразы об отсутствии требований")

if errors:
    print("VERIFY FAIL runtime:")
    for e in errors:
        print(" -", e)
    raise SystemExit(1)

print("runtime UX markers: ok")
PY

# Бот должен быть запущен
if ! docker compose -f "$COMPOSE_FILE" --env-file .env ps --status running --services | grep -qx bot; then
  fail "сервис bot не в статусе running"
fi
echo "bot: running"

# Карточка бота в Telegram (экран до /start)
docker compose -f "$COMPOSE_FILE" --env-file .env exec -T bot python - <<'PY' || fail "не удалось обновить описание бота в Telegram"
import asyncio
from aiogram import Bot
from app.bot.profile import BOT_DESCRIPTION, BOT_SHORT_DESCRIPTION
from app.core.config import get_settings

async def main() -> None:
    token = get_settings().telegram_bot_token
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN пуст")
    bot = Bot(token=token)
    try:
        await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)
        await bot.set_my_description(BOT_DESCRIPTION)
        print("telegram profile: ok")
    finally:
        await bot.session.close()

asyncio.run(main())
PY

echo "=== verify OK (sha=$SHORT_LOCAL) ==="
