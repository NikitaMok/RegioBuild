from __future__ import annotations

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.llm.base import LLMProvider, LLMProviderError


class YandexGPTProvider(LLMProvider):
    name = "yandexgpt"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.yandex_api_key or not settings.yandex_folder_id:
            raise LLMProviderError(
                "YANDEX_API_KEY и/или YANDEX_FOLDER_ID не заданы в .env. Ключ создаётся в "
                "Yandex Cloud: https://yandex.cloud/ru/docs/foundation-models/"
            )
        self._api_key = settings.yandex_api_key
        self._folder_id = settings.yandex_folder_id
        self._model = settings.yandex_model

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        from yandex_cloud_ml_sdk import YCloudML

        try:
            sdk = YCloudML(folder_id=self._folder_id, auth=self._api_key)
            model = sdk.models.completions(self._model).configure(temperature=temperature)
            result = model.run([
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt},
            ])
            return result[0].text
        except Exception as exc:
            logger.error(f"YandexGPT API вернул ошибку: {exc}")
            raise LLMProviderError(str(exc)) from exc
