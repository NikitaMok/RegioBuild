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

# Ключевые пользовательские формулировки — именно в RUNNING контейнере, не только на диске
docker compose -f "$COMPOSE_FILE" --env-file .env exec -T api python - <<'PY'
from app.core.legal import DISCLAIMER_TEXT
from app.bot.handlers.common import WELCOME_TEXT, RULES_TEXT
from app.agent.nodes import _render_extraction, _polish_response_text, _MISSING_REGION_VALUE
from app.llm.schemas import ExtractionResult, RequirementItem

errors = []

if "Уважаемый пользователь!" not in WELCOME_TEXT:
    errors.append("WELCOME: нет «Уважаемый пользователь!»")
if "Уважаемый пользователь:" in WELCOME_TEXT:
    errors.append("WELCOME: лишнее двоеточие у обращения")
if "Состав нормативных материалов:" not in RULES_TEXT:
    errors.append("RULES: нет двоеточия у «Состав нормативных материалов»")
if "Вышеуказанные сведения носят справочный характер!" not in DISCLAIMER_TEXT:
    errors.append("DISCLAIMER: нет нового заголовка")
if "<i>" not in DISCLAIMER_TEXT:
    errors.append("DISCLAIMER: нет курсива")
if "Справочный характер сведений</b>." in DISCLAIMER_TEXT:
    errors.append("DISCLAIMER: старая формулировка всё ещё в коде")

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
if "Федеральные требования" not in text:
    errors.append("RENDER: нет «Федеральные требования»")
if "Региональный уровень" in text or "Федеральный уровень" in text:
    errors.append("RENDER: старое слово «уровень» всё ещё в ответе")
if "Дополнительно применяются федеральные нормы" in text:
    errors.append("RENDER: менторская фраза про федеральные нормы")

if "специальные требования по указанному вопросу не установлены" not in _MISSING_REGION_VALUE.lower():
    errors.append("MISSING: нет юридической фразы об отсутствии требований")

junk = _polish_response_text("норма\n### /с/ /с/ /с/ /с/\nконец")
if "/с/" in junk or "###" in junk:
    errors.append("POLISH: артефакт /с/ не вырезается")

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

echo "=== verify OK (sha=$SHORT_LOCAL) ==="
