from __future__ import annotations

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.llm.base import DEFAULT_MAX_TOKENS, LLMProvider, LLMProviderError


class GigaChatProvider(LLMProvider):
    name = "gigachat"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gigachat_credentials:
            raise LLMProviderError(
                "GIGACHAT_CREDENTIALS не задан в .env. Ключ авторизации выдаётся в личном "
                "кабинете https://developers.sber.ru/portal/products/gigachat-api"
            )
        self._credentials = settings.gigachat_credentials
        self._scope = settings.gigachat_scope
        self._model = settings.gigachat_model
        self._verify_ssl_certs = settings.gigachat_verify_ssl_certs

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        from gigachat import GigaChat
        from gigachat.models import Chat, Messages, MessagesRole

        try:
            with GigaChat(
                credentials=self._credentials,
                scope=self._scope,
                model=self._model,
                verify_ssl_certs=self._verify_ssl_certs,
            ) as client:
                chat = Chat(
                    messages=[
                        Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                        Messages(role=MessagesRole.USER, content=user_prompt),
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                response = client.chat(chat)
                return response.choices[0].message.content
        except Exception as exc:
            logger.error(f"GigaChat API вернул ошибку: {exc}")
            raise LLMProviderError(str(exc)) from exc
