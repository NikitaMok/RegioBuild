from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # env из окружения/панели перекрывает значения из .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    database_url: str = "sqlite:///./regiobuild.db"

    chroma_persist_dir: str = str(BASE_DIR / "data" / "chroma")
    chroma_collection: str = "rngp_requirements"

    # MiniLM: mpnet на ~1 ГБ RAM (Bothost Basic) не влезал
    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    llm_provider: Literal["gigachat", "yandexgpt"] = "gigachat"

    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2-Pro"
    # у GigaChat свой корень НУЦ — без флага SSL-проверка падает
    gigachat_verify_ssl_certs: bool = False

    yandex_api_key: str = ""
    yandex_folder_id: str = ""
    yandex_model: str = "yandexgpt/latest"

    telegram_bot_token: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"

    log_level: str = "INFO"
    log_json: bool = False

    daily_query_limit: int = 30

    llm_cache_enabled: bool = True
    llm_cache_size: int = 256

    sentry_dsn: str = ""

    # 10 категорий коммерческого ответа; старые коды coercятся в schemas
    requirement_categories: tuple[str, ...] = (
        "земельно_правовые",
        "градостроительные",
        "пожарная_безопасность",
        "санитарные_экологические",
        "архитектурный_облик",
        "дорожное_согласование",
        "налоги_поддержка",
        "процедуры_согласования",
        "подключение_к_сетям",
        "сроки_и_документы",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
