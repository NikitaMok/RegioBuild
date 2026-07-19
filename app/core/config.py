from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # переменные окружения (Bothost-панель) важнее локального .env —
    # иначе на хостинге можно залипнуть на старом API_BASE_URL из файла
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    database_url: str = "sqlite:///./regiobuild.db"

    chroma_persist_dir: str = str(BASE_DIR / "data" / "chroma")
    chroma_collection: str = "rngp_requirements"

    # MiniLM вместо mpnet-base: на Bothost Basic (~1 ГБ RAM) тяжёлая модель
    # убивает процесс при первом /compare (502). На русском MiniLM чуть слабее
    # по качеству retrieval, но реально влезает в память вместе с FastAPI/Chroma.
    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    llm_provider: Literal["gigachat", "yandexgpt"] = "gigachat"

    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2-Pro"
    # у GigaChat самоподписанный сертификат НУЦ Минцифры, без этого флага
    # requests падает на SSL до тех пор, пока не поставишь корневой сертификат руками
    gigachat_verify_ssl_certs: bool = False

    yandex_api_key: str = ""
    yandex_folder_id: str = ""
    yandex_model: str = "yandexgpt/latest"

    telegram_bot_token: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"

    log_level: str = "INFO"

    # список регионов живёт в app/core/regions.py — дублировать его здесь незачем
    requirement_categories: tuple[str, ...] = (
        "сроки",
        "документы",
        "подключение_к_сетям",
        "состав_проекта",
        "иные_требования",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
