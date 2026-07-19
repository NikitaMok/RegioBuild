from __future__ import annotations

from pathlib import Path

import requests
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.regions import RegionDocument

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


class FetchError(RuntimeError):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.RequestException),
)
def _download(url: str, timeout: int = 20) -> bytes:
    response = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.content


def fetch_region_document(doc: RegionDocument, force: bool = False) -> Path:
    """Скачивает нормативный документ и возвращает путь к локальной копии.

    Правовые сайты (meganorm.ru, docs.cntd.ru и т.п.) не всегда пускают ботов,
    поэтому если скачать не удалось — файл можно положить руками в data/raw
    под именем из doc.local_raw_filename, и пайплайн подхватит его при
    следующем запуске.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    local_path = RAW_DIR / doc.local_raw_filename

    if local_path.exists() and not force:
        logger.info(f"[{doc.code}] уже скачан, использую {local_path}")
        return local_path

    logger.info(f"[{doc.code}] скачиваю {doc.source_url}")
    try:
        content = _download(doc.source_url)
    except requests.RequestException as exc:
        raise FetchError(
            f"не удалось скачать документ региона '{doc.code}' с {doc.source_url}: {exc}. "
            f"Сохраните страницу/файл вручную как {local_path} и запустите пайплайн ещё раз."
        ) from exc

    # .docx — это zip-архив (сигнатура PK), а по прямой ссылке на скачивание сайт
    # иногда вместо файла отдаёт html-страницу (редирект, форма подтверждения и т.п.).
    # Лучше явно на это указать, чем дать python-docx упасть с непонятной ошибкой позже.
    if doc.fetch_format == "docx" and not content.startswith(b"PK"):
        raise FetchError(
            f"по ссылке {doc.source_url} для региона '{doc.code}' пришёл не .docx-файл "
            f"(похоже на HTML-страницу, а не прямую ссылку на скачивание). "
            f"Скачайте файл вручную в браузере и положите как {local_path}."
        )

    local_path.write_bytes(content)
    logger.info(f"[{doc.code}] сохранено {len(content)} байт в {local_path}")
    return local_path
